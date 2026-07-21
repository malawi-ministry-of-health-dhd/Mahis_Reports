import json
import os
import uuid
import pandas as pd
from datetime import datetime

path = os.getcwd()
dashboards_json_path = os.path.join(path, 'data', 'visualizations', 'validated_dashboard.json')
_ds_config_path = os.path.join(path, 'configurations.json')
_ssh_dir        = os.path.join(path, 'ssh')


def load_dashboards_from_file():
    try:
        with open(dashboards_json_path, 'r') as f:
            data = json.load(f)
            return data if isinstance(data, list) else [data]
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_dashboards_to_file(data):
    with open(dashboards_json_path, 'w') as f:
        json.dump(data, f, indent=2)

def _coerce_list(value):
    if value in (None, "", []):
        return []
    if isinstance(value, list):
        return [v for v in value if v not in (None, "")]
    return [value]

def _normalize_filter_value(value):
    if isinstance(value, list):
        cleaned = [v for v in value if v not in (None, "")]
        if not cleaned:
            return []
        return cleaned
    if value in (None, ""):
        return ""
    return value

def _safe_json_loads(raw_value, default):
    if raw_value in (None, "", []):
        return default
    if isinstance(raw_value, (dict, list)):
        return raw_value
    try:
        return json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return default

def _empty_dashboard_structure(report_id, report_name, date_created):
    return {
        "report_id": report_id or f"report_{uuid.uuid4().hex[:8]}",
        "report_name": report_name or "New Dashboard",
        "date_created": date_created or datetime.now().strftime("%Y-%m-%d"),
        "visualization_types": {
            "counts": [],
            "charts": {
                "sections": []
            }
        }
    }

def _find_dashboard_index(dashboards_data, selector_value=None, report_id=None):
    if isinstance(selector_value, int) and 0 <= selector_value < len(dashboards_data):
        return selector_value
    if report_id:
        for idx, dashboard in enumerate(dashboards_data):
            if dashboard.get("report_id") == report_id:
                return idx
    return None

def _ensure_dashboard_for_edit(selector_value, report_id, report_name, date_created):
    dashboards_data = load_dashboards_from_file()
    dashboard_index = _find_dashboard_index(dashboards_data, selector_value, report_id)

    if dashboard_index is None:
        dashboard = _empty_dashboard_structure(report_id, report_name, date_created)
        dashboards_data.append(dashboard)
        dashboard_index = len(dashboards_data) - 1
        save_dashboards_to_file(dashboards_data)
    else:
        dashboard = dashboards_data[dashboard_index]
        dashboard.setdefault("visualization_types", {})
        dashboard["visualization_types"].setdefault("counts", [])
        dashboard["visualization_types"].setdefault("charts", {})
        dashboard["visualization_types"]["charts"].setdefault("sections", [])

    return dashboards_data, dashboards_data[dashboard_index], dashboard_index

def _dashboard_selector_options(dashboards_data):
    return [{"label": f"📋 {d.get('report_name', 'Unnamed')}", "value": i}
            for i, d in enumerate(dashboards_data)] + [
                {"label": "➕ Create New Dashboard", "value": "new"}
            ]

def _load_datasources():
    try:
        with open(_ds_config_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_datasources(data):
    with open(_ds_config_path, 'w') as f:
        json.dump(data, f, indent=2)


def _list_ssh_keys():
    """Return .pem/.cer/.key filenames from the project ssh/ directory."""
    if not os.path.isdir(_ssh_dir):
        return []
    return sorted(
        f for f in os.listdir(_ssh_dir)
        if f.endswith(('.pem', '.cer', '.key'))
    )


def _load_user_csv(route):
    _users_csv_path        = os.path.join(path, f'data/{route}', 'single_tables', 'users_data.csv')
    if not os.path.exists(_users_csv_path):
        return pd.DataFrame(columns=['User', 'uuid', 'role'])
    df = pd.read_csv(_users_csv_path)
    df = df.dropna(subset=['User']).drop_duplicates(subset=['User'])
    return df

def _load_user_props(route):
    _user_props_path       = os.path.join(path, f'data/{route}', 'dcc_dropdown_json', 'user_properties.json')
    if not os.path.exists(_user_props_path):
        return {"users": []}
    try:
        with open(_user_props_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"users": []}

def _save_user_props(data, route):
    _user_props_path       = os.path.join(path, f'data/{route}', 'dcc_dropdown_json', 'user_properties.json')
    os.makedirs(os.path.dirname(_user_props_path), exist_ok=True)
    with open(_user_props_path, 'w') as f:
        json.dump(data, f, indent=2)

def _load_facilities(route):
    _facilities_json_path  = os.path.join(path, f'data/{route}', 'dcc_dropdown_json', 'facilities_dropdowns.json')
    try:
        with open(_facilities_json_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _extract_identifiers(sql: str) -> list[str]:
    """Return word-like tokens from SQL that could be column names."""
    import re as _re
    # Remove string literals and comments first
    sql_clean = _re.sub(r"'[^']*'", " ", sql)
    sql_clean = _re.sub(r'"[^"]*"', " ", sql_clean)
    sql_clean = _re.sub(r"--[^\n]*", " ", sql_clean)
    # SQL keywords to skip
    _KEYWORDS = {
        "select","from","where","and","or","not","in","is","null","like","data",
        "limit","offset","group","by","order","having","join","on","as",
        "distinct","count","sum","avg","min","max","between","case","when",
        "then","else","end","with","inner","left","right","outer","cross",
        "union","all","insert","update","delete","create","drop","cast",
        "timestamp","date","interval","true","false","asc","desc","exists",
    }
    tokens = _re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql_clean)
    return [t for t in tokens if t.lower() not in _KEYWORDS]
