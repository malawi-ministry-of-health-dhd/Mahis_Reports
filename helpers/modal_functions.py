import dash
from dash import html, dcc, dash_table, Input, Output, State, callback
from dash_iconify import DashIconify
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
if os.path.exists(path_dcc_json):
    with open(path_dcc_json) as r:
        dcc_json = json.load(r)
else:
    dcc_json = {
        "programs": [],
        "encounters": [],
        "concepts": []
    }

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
        required_sheets = ['VARIABLE_NAMES', 'FILTERS', 'REPORT_NAME']
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
                # paused for now
                # if len(selected_values) > 0:
                #     return False, f"The following filter values in counts are invalid data columns: {', '.join(selected_values)}"

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
                    # paused for now
                    # if len(selected_values) > 0:
                    #     return False, f"The following filter values in charts are invalid data columns: {', '.join(selected_values)}"

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
                    # Pause this for now
                    # if invalid_columns:
                    #     return False, f"The following MNID filter values are invalid data columns: {', '.join(invalid_columns)}"
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

_DROPDOWN_BACKED_VARS = {
    "Program":         ("programs",   True),
    "Encounter":       ("encounters", True),
    "concept_name":    ("concepts",   True),
    "obs_value_coded": ("concept_answers", True),
    "Gender":          ("gender",     False),
    "DrugName":        ("DrugName",   True),
}


def _val_input(count_idx, fi, var, val):
    """Return a dropdown or text input for the filter value depending on column type."""
    backed = _DROPDOWN_BACKED_VARS.get(var)
    if backed:
        key, is_multi = backed
        opts = [{"label": v, "value": v} for v in (dcc_json.get(key) or [])]
        existing = val if isinstance(val, list) else ([val] if val else None)
        return dcc.Dropdown(
            id={"type": "count-val", "count": count_idx, "filter": fi},
            value=existing,
            options=opts,
            placeholder="Select value(s)",
            className="form-input",
            multi=is_multi,
            clearable=True,
            style={"flex": "1"},
        )
    return dcc.Input(
        id={"type": "count-val", "count": count_idx, "filter": fi},
        value=str(val) if val not in (None, "") else "",
        placeholder="Value (use * prefix for wildcard)",
        className="form-input",
        type="text",
        style={"flex": "1"},
    )


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
                _val_input(count_idx, fi, var, val),
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

# ---------------------------------------------------------------------------
# UI-builder helpers moved from pages/configurations.py
# ---------------------------------------------------------------------------
from helpers.config_helper import load_dashboards_from_file

dashboards_data = load_dashboards_from_file()


def build_reports_table(data, page=1, page_size=10):
    # Filter active reports
    active_reports = [item for item in data if item.get("archived", "False") == "False"]

    # Pagination calculations
    total = len(active_reports)
    start = (page - 1) * page_size
    end = start + page_size

    paginated_items = active_reports[start:end]

    # Modern styled header
    table_header = html.Thead(
        html.Tr([
            html.Th("#", className="report-table-header", style={"width": "50px"}),
            html.Th("Report Name", style={"text-align":"left"}),
            html.Th("Short Name", style={"text-align":"left"}),
            html.Th("Creator", style={"text-align":"left"}),
            html.Th("Date Updated", style={"text-align":"left"}),
            # html.Th("Report Type", style={"text-align":"left"}),
            html.Th("Actions", style={"text-align":"left"}),
        ])
    )

    # Build rows with modern styling
    start_row_number = (page - 1) * page_size + 1
    table_rows = []
    for idx, item in enumerate(paginated_items):
        row_number = start_row_number + idx
        table_rows.append(
            html.Tr(
                className="report-table-row",
                children=[
                    html.Td(row_number, className="report-table-cell", style={"textAlign": "center", "fontWeight": "500"}),
                    html.Td(item.get("report_name").upper(), className="report-table-cell"),
                    html.Td(item.get("page_name"), className="report-table-cell"),
                    html.Td(item.get("creator"), className="report-table-cell"),
                    html.Td(item.get("date_updated"), className="report-table-cell"),
                    # html.Td(item.get("kind","dataset"), className="report-table-cell"),
                    html.Td(
                        className="report-table-actions",
                        style={"gap":"5px"},
                        children=[
                            html.Button(
                                "✏️",
                                id={"type": "edit-btn", "index": item.get("report_id")},
                                className="action-btn edit-btn"
                            ),
                            html.Button(
                                "Archive",
                                id={"type": "archive-btn", "index": item.get("report_id")},
                                className="action-btn archive-btn"
                            ),
                            html.Button(
                                "⬇️",
                                id={"type": "download-btn", "index": item.get("report_id")},
                                className="action-btn download-btn"
                            ),
                        ]
                    ),
                ]
            )
        )

    table_body = html.Tbody(table_rows)

    return html.Div(
        className="reports-table-wrapper",
        children=[
            html.Div(
                className="reports-header",
                children=[
                    html.H2("Dataset Reports", className="reports-title"),
                    html.P(
                        "These are HMIS dataset reports. To update, click Edit or upload a report template bearing the same page_name (id)",
                        className="reports-description"
                    ),
                ]
            ),

            # Table Output
            html.Table(
                [table_header, table_body],
                className="reports-table"
            ),

            # Pagination controls
            html.Div(
                className="pagination-controls",
                children=[
                    html.Button(
                        "Previous",
                        id="prev-page",
                        n_clicks=0,
                        className="pagination-btn"
                    ),
                    html.Button(
                        "Next",
                        id="next-page",
                        n_clicks=0,
                        className="pagination-btn"
                    ),
                    html.Span(
                        f"Page {page} / { (total // page_size) + (1 if total % page_size else 0) }",
                        id="page-label",
                        className="pagination-info"
                    ),
                ]
            ),
        ]
    )


def create_editable_table(df, sheet_name):
    """Create an editable Dash DataTable from DataFrame"""
    columns = [{"name": col, "id": col} for col in df.columns]

    # Convert DataFrame to dictionary for DataTable
    data = df.to_dict('records')

    return html.Div([
        html.H4(f"Sheet: {sheet_name}", style={'marginBottom': '10px'}),
        dash_table.DataTable(
            id={'type': 'editable-table', 'sheet': sheet_name},
            columns=columns,
            data=data,
            editable=True,
            filter_action="native",
            sort_action="native",
            page_action="native",
            page_current=0,
            page_size=10,
            style_table={'overflowX': 'auto'},
            style_cell={
                'minWidth': '100px', 'width': '150px', 'maxWidth': '300px',
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
            },
            style_header={
                'backgroundColor': 'rgb(230, 230, 230)',
                'fontWeight': 'bold'
            },
        )
    ], style={'marginBottom': '20px'})


def create_preview_table(df):
    """Create a Dash DataTable for preview with filters"""
    columns = [{"name": col, "id": col} for col in df.columns]

    # Convert DataFrame to dictionary for DataTable
    data = df.to_dict('records')

    return dash_table.DataTable(
        id="preview-data-table-component",
        columns=columns,
        data=data,
        filter_action="native",
        sort_action="native",
        page_action="native",
        page_current=0,
        page_size=50,
        style_table={'overflowX': 'auto'},
        style_cell={
            'minWidth': '100px',
            'width': '150px',
            'maxWidth': '300px',
            'overflow': 'hidden',
            'textOverflow': 'ellipsis',
            'textAlign': 'left'
        },
        style_header={
            'backgroundColor': 'rgb(230, 230, 230)',
            'fontWeight': 'bold',
            'textAlign': 'left'
        },
        style_data={
            'whiteSpace': 'normal',
            'height': 'auto',
        },
        css=[{
            'selector': '.dash-spreadsheet td div',
            'rule': '''
                line-height: 15px;
                max-height: 30px; min-height: 30px; height: 30px;
                display: block;
                overflow-y: hidden;
            '''
        }]
    )


def generate_dashboard_items_list(dashboard):
    """Generate the HTML for dashboard items list"""
    counts = dashboard.get('visualization_types', {}).get('counts', [])
    sections = dashboard.get('visualization_types', {}).get('charts', {}).get('sections', [])
    priority_indicators = dashboard.get('priority_indicators', [])

    if not counts and not sections and not priority_indicators:
        return html.Div(
            className="empty-items",
            children=[
                html.Div(style={"textAlign": "center", "padding": "40px", "color": "#999"}, children=[
                    html.I(className="fas fa-chart-line", style={"fontSize": "48px"}),
                    html.P("No dashboard items yet", style={"marginTop": "16px"}),
                    html.P("Add counts or sections to get started", style={"fontSize": "12px"})
                ])
            ]
        )

    items_list = []

    for idx, indicator in enumerate(priority_indicators):
        items_list.append(
            html.Div(
                className="list-item",
                key=f"mnid-indicator-{idx}",
                children=[
                    html.Div(className="list-item-icon", children=[html.I(className="fas fa-bullseye")]),
                    html.Div(className="list-item-content", children=[
                        html.Div(className="list-title", children=indicator.get("label", f"MNID Indicator {idx + 1}")),
                        html.Div(indicator.get("category", "MNID"), style={"fontSize": "12px", "color": "#6b7280"}),
                    ]),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "padding": "12px",
                    "marginBottom": "8px",
                    "backgroundColor": "#f4f8ff",
                    "borderRadius": "6px",
                    "border": "1px solid #dbeafe"
                }
            )
        )

    # Add counts to the list
    for idx, count in enumerate(counts):
        items_list.append(
            html.Div(
                className="list-item",
                key=f"count-{idx}",
                children=[
                    html.Div(className="list-item-icon", children=[
                        html.I(className="fas fa-calculator")
                    ]),
                    html.Div(className="list-item-content", children=[
                        html.Div(className="list-title", children=count.get("name", f"{idx + 1}"))
                    ]),
                    html.Div(className="list-item-actions", children=[
                        html.Button(
                            "✏️",
                            id={"type": "count-edit", "index": idx},
                            n_clicks=0
                        ),
                        # html.Button(
                        #     "🗑",
                        #     id={"type": "count-delete", "index": idx},
                        #     n_clicks=0
                        # )
                    ])
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "padding": "12px",
                    "marginBottom": "8px",
                    "backgroundColor": "#f8f9fa",
                    "borderRadius": "6px",
                    "border": "1px solid #e9ecef"
                }
            )
        )

    # Add sections and their charts to the list
    for section_idx, section in enumerate(sections):
        # Add section header
        items_list.append(
            html.Div(
                className="list-item section-item",
                key=f"section-{section_idx}",
                children=[
                    html.Div(className="list-item-icon", children=[
                        html.I(className="fas fa-folder")
                    ]),
                    html.Div(className="list-item-content", children=[
                        html.Div(className="list-item-name", children=section.get("section_name", f"Section {section_idx + 1}"))
                    ]),
                    html.Div(className="list-item-actions", children=[
                        html.Button(
                            "✏️",
                            id={"type": "section-edit", "index": section_idx},
                            n_clicks=0,
                        ),
                        # html.Button(
                        #     "🗑",
                        #     id={"type": "section-delete", "index": section_idx},
                        #     n_clicks=0,
                        # )
                    ])
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "padding": "12px",
                    "marginBottom": "8px",
                    "backgroundColor": "#e8f4f8",
                    "borderRadius": "6px",
                    "border": "1px solid #cce5f0"
                }
            )
        )

        # Add charts within the section
        for chart_idx, chart in enumerate(section.get("items", [])):
            items_list.append(
                html.Div(
                    className="list-item chart-item",
                    key=f"section-{section_idx}-chart-{chart_idx}",
                    children=[
                        html.Div(className="list-item-icon", style={"marginLeft": "24px"}, children=[
                            html.I(className="fas fa-chart-bar")
                        ]),
                        html.Div(className="list-item-content", children=[
                            html.Div(className="list-title", children=chart.get("name", f"Chart {chart_idx + 1}"))
                        ]),
                        html.Div(className="list-item-actions", children=[
                            html.Button(
                                "✏️",
                                id={"type": "chart-edit", "section": section_idx, "chart": chart_idx},
                                n_clicks=0,
                            ),
                            # html.Button(
                            #     "🗑",
                            #     id={"type": "chart-delete", "section": section_idx, "chart": chart_idx},
                            #     n_clicks=0,
                            # )
                        ])
                    ],
                    style={
                        "display": "flex",
                        "alignItems": "center",
                        "padding": "12px",
                        "marginBottom": "8px",
                        "marginLeft": "24px",
                        "backgroundColor": "#ffffff",
                        "borderRadius": "6px",
                        "border": "1px solid #e9ecef"
                    }
                )
            )
    return html.Div(className="list-items", children=items_list)


# FOR DASHBOARDS
def create_edit_modal():
    selected_dashboard_index = 0  # Default index, will be updated by callbacks
    current_dashboard = None
    if dashboards_data and len(dashboards_data) > selected_dashboard_index:
        current_dashboard = dashboards_data[selected_dashboard_index]
    else:
        current_dashboard = {"counts": [], "sections": [], "report_name": "", "report_id": "", "date_created": ""}
    list_items_html = generate_dashboard_items_list(current_dashboard)

    return html.Div([
        # Modal backdrop
        html.Div(
            id="modal-backdrop",
            className="modal-backdrop", 
            style={"display": "none"}
        ),
        # Modal content
        html.Div(
            id="modal-content",
            className="modal-content",
            style={"display": "none"},
            children=[
                # Modal Header with Cancel button
                html.Div(
                    className="modal-header",
                    children=[
                        html.H3("Dashboard Configuration", className="modal-title"),
                        html.Button(
                            DashIconify(icon="lucide:x", width=18, height=18),
                            id="cancel-btn",
                            n_clicks=0,
                            className="modal-close-btn",
                            title="Close"
                        )
                    ]
                ),

                # Modal Body
                html.Div(
                    className="modal-body",
                    children=[
                        html.Div(
                            style={
                                "display": "flex",
                                "gap": "20px",
                                "width": "100%",
                                "height": "100%",
                            },
                            children=[
                                # ── LEFT PANEL: Setup + Items list ──────────────
                                html.Div(
                                    style={
                                        "flex": "0 0 360px",
                                        "display": "flex",
                                        "flexDirection": "column",
                                        "gap": "16px",
                                        "height": "100%",
                                        "overflow": "hidden",
                                    },
                                    children=[
                                        # Dashboard Setup Card
                                        html.Div(className="dashboard-card", style={"flexShrink": "0"}, children=[
                                            html.Div(className="dashboard-card-header", children=[
                                                html.H4("Dashboard Setup", className="dashboard-card-title"),
                                            ]),
                                            html.Div(className="dashboard-card-body", style={"overflowY": "auto", "maxHeight": "380px"}, children=[
                                                html.Div(className="form-group", children=[
                                                    html.Label("Select Dashboard:", className="form-label"),
                                                    dcc.Dropdown(
                                                        id="dashboard-selector",
                                                        options=[{"label": d.get("report_name", "Unnamed"),
                                                                  "value": i} for i, d in enumerate(dashboards_data)] +
                                                                 [{"label": "➕ Create New Dashboard", "value": "new"}],
                                                        value="new" if not dashboards_data else 0,
                                                        className="modern-dropdown",
                                                        clearable=False,
                                                    ),
                                                ]),
                                                html.Div(className="form-group", children=[
                                                    html.Label("Report Name *", className="form-label"),
                                                    dcc.Input(
                                                        id="report-name-input",
                                                        type="text",
                                                        placeholder="Enter report name...",
                                                        className="modern-input",
                                                    ),
                                                ]),
                                                html.Div(className="form-row", children=[
                                                    html.Div(className="form-group", style={"flex": "1"}, children=[
                                                        html.Label("Report ID:", className="form-label-disabled"),
                                                        dcc.Input(
                                                            id="report-id-input",
                                                            type="text",
                                                            placeholder="auto-generated",
                                                            disabled=True,
                                                            className="modern-input-disabled",
                                                        ),
                                                    ]),
                                                    html.Div(className="form-group", style={"flex": "1"}, children=[
                                                        html.Label("Date Created:", className="form-label-disabled"),
                                                        dcc.Input(
                                                            id="date-created-input",
                                                            type="text",
                                                            disabled=True,
                                                            className="modern-input-disabled",
                                                        ),
                                                    ]),
                                                ]),
                                                html.Div(style={"display": "flex", "gap": "12px"}, children=[
                                                    html.Div(className="form-group", style={"flex": "1"}, children=[
                                                        html.Label("Dashboard Type", className="form-label"),
                                                        dcc.Dropdown(
                                                            id="dashboard-type-selector",
                                                            options=[
                                                                {"label": "Standard", "value": "standard"},
                                                                {"label": "MNID Outlook", "value": "mnid"},
                                                            ],
                                                            value="standard",
                                                            clearable=False,
                                                            className="modern-dropdown",
                                                        ),
                                                    ]),
                                                    html.Div(className="form-group", style={"flex": "0 0 110px"}, children=[
                                                        html.Label("Counts/Row", className="form-label"),
                                                        dcc.Input(
                                                            id="count-items-per-row-input",
                                                            type="number",
                                                            min=1, max=8,
                                                            value=5,
                                                            placeholder="5",
                                                            className="modern-input",
                                                        ),
                                                    ]),
                                                ]),
                                                # MNID fields — hidden unless type == "mnid"
                                                html.Div(
                                                    id="mnid-section",
                                                    style={"display": "none"},
                                                    children=[
                                                        html.Div(className="form-group", children=[
                                                            html.Label("MNID Categories", className="form-label"),
                                                            dcc.Dropdown(
                                                                id="mnid-categories-selector",
                                                                options=[{"label": item, "value": item}
                                                                         for item in ["ANC", "Labour", "PNC", "Newborn"]],
                                                                value=[],
                                                                multi=True,
                                                                placeholder="Select MNID program areas",
                                                                className="modern-dropdown",
                                                            ),
                                                        ]),
                                                        html.Div(className="form-group", children=[
                                                            html.Label("MNID Indicators", className="form-label"),
                                                            html.Div(
                                                                style={"display": "flex", "justifyContent": "space-between",
                                                                       "alignItems": "center", "marginBottom": "8px"},
                                                                children=[
                                                                    html.Span("Build indicators, review JSON below.",
                                                                              style={"fontSize": "12px", "color": "#6b7280"}),
                                                                    html.Button("➕ Add Indicator",
                                                                                id="add-mnid-indicator-btn",
                                                                                n_clicks=0,
                                                                                className="btn-primary-modern"),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                id="mnid-indicators-container",
                                                                className="dashboard-card-body",
                                                                style={"maxHeight": "260px", "overflowY": "auto",
                                                                       "marginBottom": "8px", "padding": "8px",
                                                                       "border": "1px solid #e5e7eb", "borderRadius": "8px",
                                                                       "background": "#fafafa"},
                                                            ),
                                                            dcc.Textarea(
                                                                id="mnid-indicators-input",
                                                                value="",
                                                                placeholder='[{"id":"mnid_x_001","label":"...","category":"ANC",...}]',
                                                                className="modern-input",
                                                                style={"minHeight": "100px", "resize": "vertical"},
                                                            ),
                                                        ]),
                                                    ],
                                                ),
                                            ]),
                                        ]),

                                        # Dashboard Items Card (takes remaining height)
                                        html.Div(
                                            className="dashboard-card",
                                            style={"flex": "1", "display": "flex", "flexDirection": "column", "minHeight": "0"},
                                            children=[
                                                html.Div(
                                                    className="dashboard-card-header",
                                                    style={"display": "flex", "alignItems": "center",
                                                           "justifyContent": "space-between", "flexShrink": "0"},
                                                    children=[
                                                        html.H4("Dashboard Items", className="dashboard-card-title"),
                                                        html.Div(style={"display": "flex", "gap": "6px"}, children=[
                                                            html.Button("➕ Metric",
                                                                        id="add-count-btn",
                                                                        n_clicks=0,
                                                                        className="btn-primary-modern btn-small",
                                                                        title="Add a new metric/count"),
                                                            html.Button("➕ Section",
                                                                        id="add-section-btn",
                                                                        n_clicks=0,
                                                                        className="btn-primary-modern btn-small",
                                                                        title="Add a new chart section"),
                                                        ]),
                                                    ],
                                                ),
                                                html.Div(
                                                    id="dashboard-items-container",
                                                    className="dashboard-card-body",
                                                    style={"overflowY": "auto", "flex": "1"},
                                                    children=[list_items_html],
                                                ),
                                            ],
                                        ),
                                    ],
                                ),

                                # ── RIGHT PANEL: Edit Forms ──────────────────────
                                html.Div(
                                    style={
                                        "flex": "1",
                                        "display": "flex",
                                        "flexDirection": "column",
                                        "gap": "16px",
                                        "height": "100%",
                                        "overflow": "hidden",
                                    },
                                    children=[
                                        # Panel header
                                        html.Div(
                                            className="dashboard-card",
                                            style={"flexShrink": "0", "padding": "12px 16px"},
                                            children=[
                                                html.Div(style={"display": "flex", "alignItems": "center", "gap": "10px"}, children=[
                                                    html.Span("✏️", style={"fontSize": "18px"}),
                                                    html.Div(children=[
                                                        html.H4("Edit Panel", className="dashboard-card-title",
                                                                style={"margin": "0"}),
                                                        html.Span("Click an item on the left to open its form here.",
                                                                  style={"fontSize": "12px", "color": "#6b7280"}),
                                                    ]),
                                                ]),
                                            ],
                                        ),
                                        # Count / metric edit area
                                        html.Div(
                                            id="counts-container",
                                            style={
                                                "flexShrink": "0",
                                                "overflowY": "auto",
                                                "maxHeight": "45%",
                                            },
                                        ),
                                        # Sections / charts edit area (scrollable, vertical)
                                        html.Div(
                                            id="sections-container",
                                            style={
                                                "flex": "1",
                                                "overflowY": "auto",
                                                "display": "flex",
                                                "flexDirection": "column",
                                                "gap": "12px",
                                                "minHeight": "0",
                                            },
                                        ),
                                    ],
                                ),
                            ]
                        )
                    ]
                ),

                # Modal Footer with Action Buttons
                html.Div(
                    className="modal-footer",
                    style={"display": "flex", "alignItems": "center", "gap": "10px",
                           "flexWrap": "wrap"},
                    children=[
                        html.Button(
                            "Save Dashboard",
                            id="save-btn",
                            n_clicks=0,
                            className="btn-success-modern"
                        ),
                        html.Button(
                            "Delete Dashboard",
                            id="delete-btn",
                            n_clicks=0,
                            className="btn-danger-modern"
                        ),
                        html.Span(
                            id="dashboard-save-status",
                            style={"fontSize": "12px", "color": "#6b7280", "marginLeft": "auto"},
                        ),
                    ]
                ),

                # Delete Confirmation Modal
                html.Div(
                    id="delete-confirmation-modal",
                    style={"display": "none"},
                    className="confirmation-modal-overlay",
                    children=[
                        html.Div(className="confirmation-modal", children=[
                            html.Div(className="confirmation-modal-header", children=[
                                html.H4("Confirm Delete"),
                                html.Button("×", id="close-confirmation-btn", className="confirmation-close-btn")
                            ]),
                            html.Div(className="confirmation-modal-body", children=[
                                html.P("Are you sure you want to delete this dashboard?"),
                                html.P("This action cannot be undone.", style={"color": "#dc3545", "fontSize": "14px"})
                            ]),
                            html.Div(className="confirmation-modal-footer", children=[
                                html.Button("Cancel", id="cancel-delete-btn", className="btn-secondary-modern"),
                                html.Button("Delete", id="confirm-delete-btn", className="btn-danger-modern"),
                            ])
                        ])
                    ]
                )
            ]
        )
    ])


def _build_ds_list(sources):
    if not sources:
        return html.Div("No data sources configured.",
                        style={"padding": "16px", "color": "#9ca3af",
                               "fontSize": "13px", "textAlign": "center"})
    rows = []
    for i, ds in enumerate(sources):
        bg = "#f2f9f2" if i % 2 == 0 else "#ffffff"
        rows.append(html.Div(
            style={"display": "flex", "alignItems": "center",
                   "padding": "10px 14px", "background": bg,
                   "borderBottom": "1px solid #e5e7eb", "gap": "10px"},
            children=[
                html.Div(style={"flex": "1"}, children=[
                    html.Div(ds.get("name", "Unnamed"),
                             style={"fontWeight": "600", "fontSize": "13px",
                                    "color": "#006401"}),
                    html.Div(ds.get("date_updated", ""),
                             style={"fontSize": "11px", "color": "#9ca3af"}),
                ]),
                html.Button("✏️", id={"type": "ds-edit-btn", "index": i},
                            n_clicks=0, className="btn-secondary btn-small",
                            title="Edit"),
            ],
        ))
    return html.Div(rows, style={"borderRadius": "8px", "overflow": "hidden"})


def _build_users_table(users):
    if not users:
        return html.Div(
            "No users configured yet.",
            style={"padding": "16px", "color": "#9ca3af", "fontSize": "13px",
                   "textAlign": "center"},
        )

    th_style = {
        "padding": "10px 14px", "textAlign": "left",
        "background": "#006401", "color": "#fff",
        "fontSize": "12px", "fontWeight": "600",
        "whiteSpace": "nowrap",
    }
    header = html.Thead(html.Tr([
        html.Th("Username",      style=th_style),
        html.Th("UUID",          style={**th_style, "maxWidth": "160px", "overflow": "hidden",
                                        "textOverflow": "ellipsis"}),
        html.Th("Facility Code", style=th_style),
        html.Th("Role",          style=th_style),
        html.Th("Level",         style=th_style),
        html.Th("District(s)",   style=th_style),
        html.Th("Facility Name(s)", style=th_style),
    ]))

    body_rows = []
    for i, u in enumerate(users):
        p        = u.get("properties", {})
        bg       = "#f2f9f2" if i % 2 == 0 else "#ffffff"
        td       = {"padding": "8px 14px", "fontSize": "12px",
                    "background": bg, "borderBottom": "1px solid #e5e7eb",
                    "whiteSpace": "nowrap"}

        dist     = p.get("district")      or []
        fac      = p.get("facility_name") or []
        dist_str = ", ".join(dist) if isinstance(dist, list) else (dist or "—")
        fac_str  = ", ".join(fac)  if isinstance(fac,  list) else (fac  or "—")
        uuid_val = p.get("uuid", "") or ""
        uuid_short = (uuid_val[:18] + "…") if len(uuid_val) > 20 else uuid_val

        body_rows.append(html.Tr([
            html.Td(u.get("username", ""),    style={**td, "fontWeight": "500",
                                                     "color": "#006401"}),
            html.Td(uuid_short,               style={**td, "fontFamily": "monospace",
                                                     "fontSize": "11px"},
                    title=uuid_val),
            html.Td(p.get("facility_code", "") or "—", style=td),
            html.Td(p.get("role", "")         or "—", style=td),
            html.Td(p.get("user_level", "")   or "—", style=td),
            html.Td(dist_str,                  style=td),
            html.Td(fac_str,                   style=td),
        ]))

    return html.Table(
        [header, html.Tbody(body_rows)],
        style={"width": "100%", "borderCollapse": "collapse",
               "fontSize": "13px", "tableLayout": "auto"},
    )


def create_html_report_modal():
    """Full-screen modal for the Create Reports (GUI) feature."""

    # --- Toolbar ---
    btn_style = {
        "padding": "4px 10px", "fontSize": "12px", "cursor": "pointer",
        "border": "1px solid #d1d5db", "borderRadius": "4px",
        "background": "#ffffff", "color": "#374151",
    }
    sep = html.Span("|", style={"color": "#d1d5db", "padding": "0 6px", "alignSelf": "center"})

    toolbar = html.Div(
        style={
            "display": "flex", "flexWrap": "wrap", "gap": "4px",
            "alignItems": "center", "padding": "8px 12px",
            "background": "#f3f4f6", "borderBottom": "1px solid #e5e7eb",
            "flexShrink": "0",
        },
        children=[
            # Tables group
            html.Span("Tables", style={"fontSize": "11px", "color": "#6b7280",
                                       "fontWeight": "600", "alignSelf": "center"}),
            html.Button([DashIconify(icon="lucide:plus", width=13), "New"],
                        id="rpt-add-table-btn", n_clicks=0, style=btn_style),
            html.Button([DashIconify(icon="lucide:arrow-up", width=13), " Above"],
                        id="rpt-add-above-btn", n_clicks=0, style=btn_style),
            html.Button([DashIconify(icon="lucide:arrow-down", width=13), " Below"],
                        id="rpt-add-below-btn", n_clicks=0, style=btn_style),
            html.Button([DashIconify(icon="lucide:arrow-left", width=13), " Left"],
                        id="rpt-add-left-btn", n_clicks=0, style=btn_style),
            html.Button([DashIconify(icon="lucide:arrow-right", width=13), " Right"],
                        id="rpt-add-right-btn", n_clicks=0, style=btn_style),
            sep,
            # Rows/Cols group
            html.Span("Rows/Cols", style={"fontSize": "11px", "color": "#6b7280",
                                          "fontWeight": "600", "alignSelf": "center"}),
            html.Button([DashIconify(icon="lucide:plus", width=13), "Row"],
                        id="rpt-add-row-btn", n_clicks=0, style=btn_style),
            html.Button([DashIconify(icon="lucide:minus", width=13), "Row"],
                        id="rpt-del-row-btn", n_clicks=0, style=btn_style),
            html.Button([DashIconify(icon="lucide:plus", width=13), "Col"],
                        id="rpt-add-col-btn", n_clicks=0, style=btn_style),
            html.Button([DashIconify(icon="lucide:minus", width=13), "Col"],
                        id="rpt-del-col-btn", n_clicks=0, style=btn_style),
            sep,
            # Cells group
            html.Span("Cells", style={"fontSize": "11px", "color": "#6b7280",
                                      "fontWeight": "600", "alignSelf": "center"}),
            html.Button([DashIconify(icon="lucide:merge", width=13), " Merge"],
                        id="rpt-merge-btn", n_clicks=0, style=btn_style),
            html.Button([DashIconify(icon="lucide:split", width=13), " Split"],
                        id="rpt-split-btn", n_clicks=0, style=btn_style),
            html.Button([DashIconify(icon="lucide:eraser", width=13), " Clear"],
                        id="rpt-clear-btn", n_clicks=0, style=btn_style),
            sep,
            # Style group
            html.Span("Fill:", style={"fontSize": "12px", "color": "#374151",
                                      "alignSelf": "center"}),
            dcc.Input(id="rpt-fill-color", type="text", value="#ffffff",
                      placeholder="#rrggbb",
                      style={"width": "72px", "height": "26px", "padding": "2px 4px",
                             "border": "1px solid #d1d5db", "borderRadius": "4px",
                             "fontSize": "12px", "fontFamily": "monospace"}),
            html.Button("Apply", id="rpt-apply-fill-btn", n_clicks=0, style=btn_style),
            html.Span("Font:", style={"fontSize": "12px", "color": "#374151",
                                      "alignSelf": "center"}),
            dcc.Input(id="rpt-font-color", type="text", value="#000000",
                      placeholder="#rrggbb",
                      style={"width": "72px", "height": "26px", "padding": "2px 4px",
                             "border": "1px solid #d1d5db", "borderRadius": "4px",
                             "fontSize": "12px", "fontFamily": "monospace"}),
            html.Button("Apply", id="rpt-apply-font-btn", n_clicks=0, style=btn_style),
            sep,
            # Text style group
            html.Span("Text", style={"fontSize": "11px", "color": "#6b7280",
                                     "fontWeight": "600", "alignSelf": "center"}),
            html.Button(DashIconify(icon="lucide:bold", width=13), id="rpt-bold-btn",
                        n_clicks=0, title="Bold",
                        style={**btn_style, "minWidth": "28px"}),
            html.Button(DashIconify(icon="lucide:italic", width=13), id="rpt-italic-btn",
                        n_clicks=0, title="Italic",
                        style={**btn_style, "minWidth": "28px"}),
            sep,
            # Alignment group
            html.Span("Align", style={"fontSize": "11px", "color": "#6b7280",
                                      "fontWeight": "600", "alignSelf": "center"}),
            html.Button(DashIconify(icon="lucide:align-left", width=13),
                        id="rpt-align-left-btn", n_clicks=0, title="Align left",
                        style={**btn_style, "minWidth": "34px"}),
            html.Button(DashIconify(icon="lucide:align-center", width=13),
                        id="rpt-align-center-btn", n_clicks=0, title="Align center",
                        style={**btn_style, "minWidth": "34px"}),
            html.Button(DashIconify(icon="lucide:align-right", width=13),
                        id="rpt-align-right-btn", n_clicks=0, title="Align right",
                        style={**btn_style, "minWidth": "34px"}),
            sep,
            # Indent group
            html.Span("Indent", style={"fontSize": "11px", "color": "#6b7280",
                                       "fontWeight": "600", "alignSelf": "center"}),
            html.Button(DashIconify(icon="lucide:indent", width=13), id="rpt-indent-btn",
                        n_clicks=0, title="Indent",
                        style={**btn_style, "minWidth": "32px"}),
            html.Button(DashIconify(icon="lucide:outdent", width=13), id="rpt-dedent-btn",
                        n_clicks=0, title="Dedent",
                        style={**btn_style, "minWidth": "32px"}),
            sep,
            # Title & remove
            html.Button([DashIconify(icon="lucide:heading-1", width=13), " ↑"],
                        id="rpt-title-above-btn", n_clicks=0, title="Add title above",
                        style=btn_style),
            html.Button([DashIconify(icon="lucide:heading-1", width=13), " ↓"],
                        id="rpt-title-below-btn", n_clicks=0, title="Add title below",
                        style=btn_style),
            html.Button([DashIconify(icon="lucide:trash-2", width=13), " Table"],
                        id="rpt-remove-table-btn", n_clicks=0,
                        style={**btn_style, "color": "#dc2626", "borderColor": "#fca5a5"}),
        ],
    )

    # --- Body panels ---
    left_panel = html.Div(
        style={
            "width": "30%", "flexShrink": "0", "background": "#f9fafb",
            "borderRight": "1px solid #e5e7eb", "overflowY": "auto",
            "padding": "12px",
        },
        children=[
            html.Div("Variables", style={"fontWeight": "700", "fontSize": "14px",
                                         "color": "#374151", "marginBottom": "10px"}),
            html.Div(
                "Select a report to load variables.",
                id="report-variables-panel-content",
                style={"fontSize": "12px", "color": "#9ca3af"},
            ),
        ],
    )

    # --- Table editor sub-panel (default view) ---
    table_editor = html.Div(
        id="rpt-table-editor",
        style={"display": "flex", "flexDirection": "column", "flex": "1", "minHeight": "0"},
        children=[
            toolbar,
            html.Div(
                id="html-report-canvas",
                style={
                    "flex": "1", "overflowY": "auto", "overflowX": "auto",
                    "position": "relative",
                    "backgroundColor": "#ffffff",
                    "backgroundImage": (
                        "linear-gradient(rgba(0,0,0,0.04) 1px, transparent 1px),"
                        "linear-gradient(90deg, rgba(0,0,0,0.04) 1px, transparent 1px),"
                        "linear-gradient(rgba(0,0,0,0.08) 1px, transparent 1px),"
                        "linear-gradient(90deg, rgba(0,0,0,0.08) 1px, transparent 1px)"
                    ),
                    "backgroundSize": "8px 8px, 8px 8px, 40px 40px, 40px 40px",
                    "backgroundPosition": "-1px -1px, -1px -1px, -1px -1px, -1px -1px",
                    "minHeight": "400px",
                },
                children=[],
            ),
            html.Div(
                id="html-report-status",
                style={
                    "flexShrink": "0", "padding": "4px 12px",
                    "background": "#f3f4f6", "borderTop": "1px solid #e5e7eb",
                    "fontSize": "12px", "color": "#6b7280",
                },
                children="No selection",
            ),
        ],
    )

    # --- Filter editor sub-panel (shown when a variable is clicked) ---
    _measure_opts = [{"label": m, "value": m} for m in [
        "count", "nunique", "sum", "count_set", "cohort_count", "cohort_count_set",
        "cohort_sum", "cohort_count_defaulter", "count_defaulter", "count_set_defaulter",
        "cohort_count_set_defaulter", "calculated", "calculated_intersection",
        "calculated_union", "calculated_max", "calculated_min",
    ]]
    _actual_keys_opts = [{"label": k, "value": k} for k in actual_keys_in_data]

    filter_editor = html.Div(
        id="rpt-filter-editor",
        style={"display": "none", "flex": "1", "flexDirection": "column", "minHeight": "0"},
        children=[
            # Header bar
            html.Div(
                style={
                    "display": "flex", "alignItems": "center", "gap": "8px",
                    "padding": "8px 12px", "background": "#f0fdf4",
                    "borderBottom": "1px solid #d1fae5", "flexShrink": "0",
                },
                children=[
                    html.Button([DashIconify(icon="lucide:arrow-left", width=13), " Back"],
                                id="rpt-flt-close-btn", n_clicks=0,
                                style={"padding": "4px 10px", "fontSize": "12px",
                                       "cursor": "pointer", "background": "#e5e7eb",
                                       "border": "1px solid #d1d5db", "borderRadius": "4px",
                                       "color": "#374151"}),
                    html.Span(id="rpt-flt-title", children="Edit Filter",
                              style={"fontWeight": "700", "fontSize": "14px",
                                     "color": "#065f46", "flex": "1"}),
                    html.Span(id="rpt-flt-status", children="",
                              style={"fontSize": "12px", "color": "#16a34a",
                                     "fontStyle": "italic"}),
                ],
            ),
            # Scrollable body
            html.Div(
                style={"flex": "1", "overflowY": "auto", "padding": "16px"},
                children=[
                    # Display name
                    html.Div(style={"marginBottom": "12px"}, children=[
                        html.Label("Display Name",
                                   style={"fontSize": "12px", "fontWeight": "600",
                                          "display": "block", "marginBottom": "4px",
                                          "color": "#374151"}),
                        dcc.Input(id="rpt-flt-filter-name-desc", value="", debounce=True,
                                  placeholder="Display name…",disabled=True,
                                  style={"width": "100%", "padding": "6px 8px",
                                         "fontSize": "13px", "border": "1px solid #d1d5db",
                                         "borderRadius": "4px", "boxSizing": "border-box"}),
                    ]),
                    # Measure
                    html.Div(style={"marginBottom": "12px"}, children=[
                        html.Label("Measure",
                                   style={"fontSize": "12px", "fontWeight": "600",
                                          "display": "block", "marginBottom": "4px",
                                          "color": "#374151"}),
                        dcc.Dropdown(id="rpt-flt-measure", options=_measure_opts, value=None,
                                     placeholder="Select measure…", clearable=True,
                                     style={"fontSize": "13px"}),
                    ]),
                    # Unique column (container swapped by callback: dropdown ↔ input)
                    html.Div(style={"marginBottom": "12px"}, children=[
                        html.Label("Unique Column",
                                   style={"fontSize": "12px", "fontWeight": "600",
                                          "display": "block", "marginBottom": "4px",
                                          "color": "#374151"}),
                        html.Div(
                            id="rpt-flt-unique-col-wrap",
                            children=[
                                dcc.Dropdown(id="rpt-flt-unique-col",
                                             options=_actual_keys_opts, value=None,
                                             placeholder="Select column…", clearable=True,
                                             style={"fontSize": "13px"}),
                            ],
                        ),
                    ]),
                    html.Hr(style={"margin": "16px 0", "borderColor": "#e5e7eb"}),
                    # Filter rows header
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "marginBottom": "6px"},
                        children=[
                            html.Span("Variable Filters",
                                      style={"fontWeight": "600", "fontSize": "13px",
                                             "color": "#374151", "flex": "1"}),
                            html.Button([DashIconify(icon="lucide:plus", width=13), " Add Row"],
                                        id="rpt-flt-add-row-btn", n_clicks=0,
                                        style={"padding": "3px 10px", "fontSize": "12px",
                                               "cursor": "pointer", "background": "#e0f2fe",
                                               "border": "1px solid #38bdf8",
                                               "borderRadius": "4px", "color": "#0c4a6e"}),
                        ],
                    ),
                    # Column labels for rows
                    html.Div(
                        style={"display": "flex", "gap": "6px", "marginBottom": "4px",
                               "fontSize": "11px", "color": "#6b7280", "fontWeight": "600"},
                        children=[
                            html.Span("Column",  style={"flex": "2", "minWidth": "120px"}),
                            html.Span("Op",      style={"flex": "0 0 80px"}),
                            html.Span("Type",    style={"flex": "0 0 80px"}),
                            html.Span("Value(s)", style={"flex": "3", "minWidth": "140px"}),
                            html.Span("",        style={"flex": "0 0 34px"}),
                        ],
                    ),
                    # Dynamic filter rows
                    html.Div(id="rpt-filter-rows-container", children=[]),
                ],
            ),
            # Footer
            html.Div(
                style={"flexShrink": "0", "padding": "8px 16px", "background": "#f9fafb",
                       "borderTop": "1px solid #e5e7eb", "display": "flex", "gap": "8px",
                       "alignItems": "center"},
                children=[
                    html.Button([DashIconify(icon="lucide:save", width=14), " Save Filter"],
                                id="rpt-flt-save-btn", n_clicks=0,
                                style={"padding": "6px 18px", "background": "#16a34a",
                                       "color": "#fff", "border": "none", "borderRadius": "5px",
                                       "cursor": "pointer", "fontSize": "13px",
                                       "fontWeight": "600"}),
                ],
            ),
        ],
    )

    right_panel = html.Div(
        style={"flex": "1", "display": "flex", "flexDirection": "column", "minWidth": "0"},
        children=[table_editor, filter_editor],
    )

    # --- Modal ---
    return html.Div(
        id="create-reports-modal",
        style={
            "display": "none",
            "position": "fixed", "top": "0", "left": "0",
            "width": "100vw", "height": "100vh",
            "zIndex": "2000",
            "alignItems": "center", "justifyContent": "center",
            "background": "rgba(0,0,0,0.45)",
        },
        children=[
            html.Div(
                style={
                    "width": "96vw", "height": "92vh",
                    "background": "#ffffff", "borderRadius": "10px",
                    "display": "flex", "flexDirection": "column",
                    "overflow": "hidden",
                    "boxShadow": "0 20px 60px rgba(0,0,0,0.35)",
                },
                children=[
                    # Header bar
                    html.Div(
                        style={
                            "display": "flex", "alignItems": "center", "gap": "12px",
                            "padding": "10px 16px",
                            "background": "#006401", "flexShrink": "0",
                        },
                        children=[
                            html.Span("Update Report",
                                      style={"fontWeight": "700", "fontSize": "16px",
                                             "color": "#ffffff", "marginRight": "8px"}),
                            dcc.Dropdown(
                                id="html-report-name",
                                options=[],
                                placeholder="Select report…",
                                clearable=True,
                                searchable=True,
                                style={
                                    "flex": "1", "maxWidth": "340px",
                                    "fontSize": "13px", "color": "#111827",
                                },
                            ),
                            html.Button([DashIconify(icon="lucide:save", width=15), " Save"],
                                        id="save-html-report-btn", n_clicks=0,
                                        style={"padding": "5px 14px", "background": "#16a34a",
                                               "color": "#fff", "border": "none",
                                               "borderRadius": "5px", "cursor": "pointer",
                                               "fontSize": "13px", "fontWeight": "600"}),
                            html.Span(id="html-report-save-status",
                                      style={"fontSize": "12px", "color": "#d1fae5",
                                             "fontStyle": "italic", "minWidth": "60px"}),
                            html.Button([DashIconify(icon="lucide:x", width=13), " Close"],
                                        id="close-create-reports-modal", n_clicks=0,
                                        style={"marginLeft": "auto", "padding": "5px 14px",
                                               "background": "transparent", "color": "#ffffff",
                                               "border": "1px solid rgba(255,255,255,0.4)",
                                               "borderRadius": "5px", "cursor": "pointer",
                                               "fontSize": "13px"}),
                        ],
                    ),
                    # Body: left + right panels
                    html.Div(
                        style={"display": "flex", "flex": "1", "overflow": "hidden"},
                        children=[left_panel, right_panel],
                    ),
                ],
            ),
        ],
    )


def create_prog_report_modal():
    """Modal for creating/editing program report configs in validated_prog_reports.json."""
    key_opts       = [{"label": k, "value": k} for k in actual_keys_in_data]
    program_opts   = [{"label": p, "value": p} for p in drop_down_programs]
    ll_aggr_opts   = [{"label": a, "value": a} for a in
                      ["join", "first", "last", "nunique", "sum", "count",
                       "mean", "min", "max", "list"]]
    piv_aggr_opts  = [{"label": a, "value": a} for a in
                      ["sum", "count", "mean", "nunique", "min", "max", "first"]]
    merge_opts     = [{"label": m, "value": m} for m in ["left", "inner", "right", "outer"]]
    type_opts      = [{"label": t, "value": t} for t in ["LineList", "PivotTable", "CrossTab"]]
    unique_opts    = [{"label": "person_id",    "value": "person_id"},
                      {"label": "encounter_id", "value": "encounter_id"}]
    normalize_opts = [{"label": n, "value": n} for n in ["all", "index", "columns"]]
    role_opts      = [{"label": r, "value": r} for r in
                      ["Any", "Clinician", "Nurse", "Admin"]]

    _i = {"width": "100%", "padding": "6px 8px", "fontSize": "12px",
          "border": "1px solid #d1d5db", "borderRadius": "4px", "boxSizing": "border-box"}
    _t = {**_i, "height": "54px", "resize": "vertical", "fontFamily": "monospace"}
    _l = {"fontSize": "11px", "fontWeight": "600", "color": "#374151",
          "display": "block", "marginBottom": "3px"}
    _s = {"marginBottom": "12px"}

    # ── LEFT PANEL ──────────────────────────────────────────────────────────
    left_panel = html.Div(
        style={"flex": "0 0 300px", "display": "flex", "flexDirection": "column",
               "height": "100%", "overflowY": "auto", "padding": "14px 12px",
               "borderRight": "1px solid #bbf7d0", "background": "#f0fdf4"},
        children=[
            html.Div(style=_s, children=[
                html.Label("Select / Search Report", style=_l),
                html.Div(style={"display": "flex", "gap": "6px"}, children=[
                    dcc.Dropdown(id="prog-rpt-selector", options=[],
                                 placeholder="Search…", clearable=True, searchable=True,
                                 style={"flex": "1", "fontSize": "12px"}),
                    html.Button([DashIconify(icon="lucide:plus", width=13), " New"],
                                id="prog-rpt-new-btn", n_clicks=0,
                                style={"padding": "4px 10px", "fontSize": "12px",
                                       "background": "#15803d", "color": "#fff",
                                       "border": "none", "borderRadius": "4px",
                                       "cursor": "pointer", "whiteSpace": "nowrap"}),
                ]),
            ]),
            html.Div(style=_s, children=[
                html.Label("ID (auto)", style={**_l, "color": "#9ca3af"}),
                dcc.Input(id="prog-rpt-id", type="text", disabled=True,
                          placeholder="auto-generated",
                          style={**_i, "background": "#f3f4f6", "color": "#9ca3af"}),
            ]),
            html.Div(style=_s, children=[
                html.Label("Report Name *", style=_l),
                dcc.Input(id="prog-rpt-name", type="text",
                          placeholder="Enter report name…", style=_i),
            ]),
            html.Div(style=_s, children=[
                html.Label("Program", style=_l),
                dcc.Dropdown(id="prog-rpt-program", options=program_opts,
                             placeholder="Select program…", clearable=True,
                             style={"fontSize": "12px"}),
            ]),
            html.Div(style=_s, children=[
                html.Label("Type *", style=_l),
                dcc.Dropdown(id="prog-rpt-type", options=type_opts,
                             placeholder="LineList / PivotTable / CrossTab…",
                             clearable=False, style={"fontSize": "12px"}),
            ]),
            html.Div(style=_s, children=[
                html.Label("Unique Value", style=_l),
                dcc.Dropdown(id="prog-rpt-unique-col", options=unique_opts,
                             placeholder="person_id / encounter_id",
                             clearable=True, style={"fontSize": "12px"}),
            ]),
            html.Div(style=_s, children=[
                html.Label("Authorized Users", style=_l),
                dcc.Dropdown(id="prog-rpt-auth-user", options=role_opts,
                             placeholder="Select roles…", multi=True, clearable=True,
                             style={"fontSize": "12px"}),
            ]),
            html.Div(style=_s, children=[
                html.Label("Message", style=_l),
                dcc.Textarea(id="prog-rpt-message", placeholder="Optional display message…",
                             style={**_t, "height": "48px"}),
            ]),
        ],
    )

    # RIGHT: LineList panel
    ll_panel = html.Div(
        id="prog-rpt-linelist-panel",
        style={"display": "none", "flexDirection": "column", "gap": "8px",
               "height": "100%", "overflowY": "auto", "padding": "14px"},
        children=[
            html.Div(style={"display": "flex", "justifyContent": "space-between",
                            "alignItems": "center", "flexShrink": "0",
                            "borderBottom": "2px solid #e5e7eb", "paddingBottom": "8px",
                            "marginBottom": "4px"}, children=[
                html.Span("Group Columns",
                          style={"fontSize": "13px", "fontWeight": "700", "color": "#1e293b"}),
                html.Button([DashIconify(icon="lucide:plus", width=13), " Add Group"],
                            id="prog-rpt-add-group-btn", n_clicks=0,
                            style={"padding": "4px 12px", "fontSize": "12px",
                                   "background": "#16a34a", "color": "#fff",
                                   "border": "none", "borderRadius": "4px",
                                   "cursor": "pointer"}),
            ]),
            html.Div(id="prog-rpt-groups-container", style={"flexShrink": "0"}),
            html.Hr(style={"margin": "6px 0", "borderColor": "#e5e7eb", "flexShrink": "0"}),
            html.Div(style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                            "flexShrink": "0"}, children=[
                html.Div(style={"flex": "2", "minWidth": "100px"}, children=[
                    html.Label("Columns Order (in display order)", style={**_l, "marginBottom": "4px"}),
                    dcc.Textarea(id="prog-rpt-cols-order",
                                 placeholder="Separated by pipe |",
                                 style={**_t, "height": "100px"}),
                ]),
                html.Div(style={"flex": "1", "minWidth": "140px"}, children=[
                    html.Label("Merge Methods (one per join)", style={**_l, "marginBottom": "4px"}),
                    dcc.Dropdown(id="prog-rpt-merge-methods", options=merge_opts,
                                 multi=True, placeholder="left / inner…",
                                 style={"fontSize": "12px","height": "100px"}),
                ]),
                html.Div(style={"flex": "1", "minWidth": "200px"}, children=[
                    html.Label("Global Rename (JSON)", style={**_l, "marginBottom": "4px"}),
                    dcc.Textarea(id="prog-rpt-rename",
                                 placeholder='{"given_name": "First Name", …}',
                                 style={**_t, "height": "100px"}),
                ]),
            ]),
        ],
    )

    # RIGHT: PivotTable / CrossTab panel
    piv_panel = html.Div(
        id="prog-rpt-pivot-panel",
        style={"display": "none", "flexDirection": "column", "gap": "10px",
               "height": "100%", "overflowY": "auto", "padding": "14px"},
        children=[
            html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr",
                            "gap": "12px", "flexShrink": "0"}, children=[
                html.Div(children=[
                    html.Label("Index Column (Rows)", style=_l),
                    dcc.Input(id="prog-rpt-index-col", type="text",
                              placeholder="e.g. DrugName", style=_i),
                ]),
                html.Div(children=[
                    html.Label("Columns", style=_l),
                    dcc.Input(id="prog-rpt-columns-col", type="text",
                              placeholder="e.g. Encounter", style=_i),
                ]),
                html.Div(children=[
                    html.Label("Values Column", style=_l),
                    dcc.Input(id="prog-rpt-values-col", type="text",
                              placeholder="e.g. ValueN", style=_i),
                ]),
                html.Div(children=[
                    html.Label("Aggregation Function", style=_l),
                    dcc.Dropdown(id="prog-rpt-aggfunc", options=piv_aggr_opts,
                                 placeholder="sum / count…", clearable=False,
                                 style={"fontSize": "12px"}),
                ]),
                html.Div(children=[
                    html.Label("Unique Column (dedup)", style=_l),
                    dcc.Dropdown(id="prog-rpt-pivot-unique-col", options=unique_opts,
                                 clearable=True, placeholder="encounter_id…",
                                 style={"fontSize": "12px"}),
                ]),
                html.Div(id="prog-rpt-normalize-wrap", style={"display": "none"}, children=[
                    html.Label("Normalize (CrossTab only)", style=_l),
                    dcc.Dropdown(id="prog-rpt-normalize", options=normalize_opts,
                                 clearable=True, placeholder="all / index / columns",
                                 style={"fontSize": "12px"}),
                ]),
            ]),
            html.Hr(style={"margin": "4px 0", "borderColor": "#e5e7eb", "flexShrink": "0"}),
            html.Span("Filters (up to 3)",
                      style={"fontSize": "12px", "fontWeight": "600", "color": "#374151",
                             "flexShrink": "0"}),
            html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                            "gap": "8px 14px", "flexShrink": "0"}, children=[
                html.Div(children=[html.Label("Filter Column 1", style=_l),
                                   dcc.Dropdown(id="prog-rpt-filter-col1", options=key_opts,
                                                clearable=True, style={"fontSize": "12px"})]),
                html.Div(children=[html.Label("Filter Value 1", style=_l),
                                   dcc.Input(id="prog-rpt-filter-val1", type="text",
                                             placeholder="Value…", style=_i)]),
                html.Div(children=[html.Label("Filter Column 2", style=_l),
                                   dcc.Dropdown(id="prog-rpt-filter-col2", options=key_opts,
                                                clearable=True, style={"fontSize": "12px"})]),
                html.Div(children=[html.Label("Filter Value 2", style=_l),
                                   dcc.Input(id="prog-rpt-filter-val2", type="text",
                                             placeholder="Value…", style=_i)]),
                html.Div(children=[html.Label("Filter Column 3", style=_l),
                                   dcc.Dropdown(id="prog-rpt-filter-col3", options=key_opts,
                                                clearable=True, style={"fontSize": "12px"})]),
                html.Div(children=[html.Label("Filter Value 3", style=_l),
                                   dcc.Input(id="prog-rpt-filter-val3", type="text",
                                             placeholder="Value…", style=_i)]),
            ]),
            html.Hr(style={"margin": "4px 0", "borderColor": "#e5e7eb", "flexShrink": "0"}),
            html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                            "gap": "12px", "flexShrink": "0"}, children=[
                html.Div(children=[html.Label("Rename (JSON)", style=_l),
                                   dcc.Textarea(id="prog-rpt-tabular-rename",
                                                placeholder='{"DrugName": "DRUG", …}',
                                                style=_t)]),
                html.Div(children=[html.Label("Replace (JSON)", style=_l),
                                   dcc.Textarea(id="prog-rpt-tabular-replace",
                                                placeholder='{"old": "new", …}',
                                                style=_t)]),
            ]),
        ],
    )

    right_panel = html.Div(
        style={"flex": "1", "display": "flex", "flexDirection": "column",
               "minWidth": "0"},
        children=[ll_panel, piv_panel],
    )

    return html.Div(
        id="prog-report-modal",
        style={"display": "none", "position": "fixed", "top": "0", "left": "0",
               "width": "100vw", "height": "100vh", "zIndex": "2000",
               "alignItems": "center", "justifyContent": "center",
               "background": "rgba(0,0,0,0.45)"},
        children=[
            html.Div(
                style={"width": "96vw", "height": "92vh", "background": "#fff",
                       "borderRadius": "10px", "display": "flex",
                       "flexDirection": "column", "overflow": "hidden",
                       "boxShadow": "0 20px 60px rgba(0,0,0,0.35)"},
                children=[
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "12px",
                               "padding": "10px 16px", "background": "#006401",
                               "flexShrink": "0"},
                        children=[
                            html.Span("Create Program Reports",
                                      style={"fontWeight": "700", "fontSize": "16px",
                                             "color": "#fff", "marginRight": "8px",
                                             "whiteSpace": "nowrap"}),
                            html.Button([DashIconify(icon="lucide:save", width=15), " Save"],
                                        id="prog-rpt-save-btn", n_clicks=0,
                                        style={"padding": "5px 14px", "background": "#16a34a",
                                               "color": "#fff", "border": "none",
                                               "borderRadius": "5px", "cursor": "pointer",
                                               "fontSize": "13px", "fontWeight": "600"}),
                            html.Button([DashIconify(icon="lucide:trash-2", width=14), " Delete"],
                                        id="prog-rpt-delete-btn", n_clicks=0,
                                        style={"padding": "5px 14px", "background": "#dc2626",
                                               "color": "#fff", "border": "none",
                                               "borderRadius": "5px", "cursor": "pointer",
                                               "fontSize": "13px"}),
                            html.Span(id="prog-rpt-status",
                                      style={"fontSize": "12px", "color": "#d1fae5",
                                             "fontStyle": "italic", "minWidth": "80px"}),
                            html.Button([DashIconify(icon="lucide:x", width=13), " Close"],
                                        id="prog-rpt-close-btn", n_clicks=0,
                                        style={"marginLeft": "auto", "padding": "5px 14px",
                                               "background": "transparent", "color": "#fff",
                                               "border": "1px solid rgba(255,255,255,0.4)",
                                               "borderRadius": "5px", "cursor": "pointer",
                                               "fontSize": "13px"}),
                        ],
                    ),
                    html.Div(
                        style={"display": "flex", "flex": "1", "overflow": "hidden"},
                        children=[left_panel, right_panel],
                    ),
                ],
            ),
        ],
    )
