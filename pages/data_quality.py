import dash
from dash import html, dcc, dash_table, Input, Output, State, callback
from dash.exceptions import PreventUpdate
import json
import math
import os
import pandas as pd
import plotly.graph_objects as go

from data_storage import DataStorage
from config import (
    PROGRAM_, FACILITY_, DISTRICT_, DATE_, PERSON_ID_, ENCOUNTER_ID_, OBS_DATETIME_,
    CONCEPT_NAME_, ENCOUNTER_,
    IDENTIFIER_, FIRST_NAME_, LAST_NAME_, GENDER_, HOME_DISTRICT_, TA_, VILLAGE_,
    BIRTHDATE_, CELL_,
)
# DISABLED: importing from another page module (pages.home) makes Dash's
# page-loader execute home.py's whole file -- including every @callback in
# it -- a second time, since Dash's own loader doesn't check sys.modules
# before re-running a page file. That registers every callback in home.py
# twice and crashes the app at startup with "Duplicate callback outputs".
# This page is already hidden from navigation, so every call site below
# falls back to a safe "unauthorized / no scope restriction" default instead
# of importing these from pages.home. See also pages/reports.py, which has
# the same import for the same reason (kept there since one of its call
# sites is a real auth check, unlike here).
# from pages.home import _resolve_user_scope, _scope_where_parts, _load_user_registry
from mnid.core.constants import BG, BORDER, TEXT
from dq.theme import BRAND, BRAND_TINT
import dq.theme  # noqa: F401 -- registers the "dq" Plotly template
from dq.checks.duplicates import (
    RULES as DUP_RULES, RULE_ORDER as DUP_RULE_ORDER, FIELD_OPTIONS as DUP_FIELD_OPTIONS,
    match_duplicates,
)

dash.register_page(__name__, path="/data_quality", title="Data Quality")

_CANDIDATES_PAGE_SIZE = 10

# Identity/Demographics core fields used for the Overview facility scorecard's
# field-completeness proxy. The Completeness tab lets the user pick any
# column set; this is a fixed, smaller stand-in so Overview has a real number
# today without duplicating that tab's column-picker logic.
CORE_FIELDS = [IDENTIFIER_, FIRST_NAME_, LAST_NAME_, GENDER_, HOME_DISTRICT_, TA_, VILLAGE_]

# The Completeness tab's own "Mandatory Demographics" picker -- (source
# column, display label) pairs a person record is evaluated against.
DEMOGRAPHIC_FIELD_OPTIONS = [
    (FIRST_NAME_, "Given name"),
    (LAST_NAME_, "Family name"),
    (GENDER_, "Gender"),
    (BIRTHDATE_, "Date of birth"),
    (HOME_DISTRICT_, "Home district"),
    (TA_, "TA"),
    (VILLAGE_, "Village"),
]

_TAB_STYLE = {
    "padding": "10px 18px",
    "border": f"1px solid {BORDER}",
    "backgroundColor": BG,
    "color": TEXT,
}
_TAB_SELECTED_STYLE = {
    "padding": "10px 18px",
    "border": f"1px solid {BRAND}",
    "backgroundColor": BRAND_TINT,
    "color": BRAND,
    "fontWeight": 700,
}


def _iso_date(value):
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _latest_full_month_window(max_date):
    """Latest full calendar month present in the data, given its max date."""
    if max_date is None or pd.isna(max_date):
        return None, None
    max_date = pd.Timestamp(max_date)
    month_start = max_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month_start = month_start + pd.DateOffset(months=1)
    if max_date < next_month_start - pd.Timedelta(days=1):
        month_start = month_start - pd.DateOffset(months=1)
        next_month_start = month_start + pd.DateOffset(months=1)
    month_end = next_month_start - pd.Timedelta(days=1)
    return month_start.date().isoformat(), month_end.date().isoformat()


def _ceiling_scope_where(level, location, user_districts):
    """WHERE parts for the user's own scope ceiling -- no user-selected narrowing."""
    # DISABLED: _scope_where_parts is from pages.home -- see the commented
    # import at the top of this file. Falls back to no scope restriction.
    # parts = _scope_where_parts(level, location, None, user_districts, None, None)
    parts = []
    return " AND ".join(parts) if parts else "1=1"


def _selection_where(level, location, user_districts, selected_districts, selected_facilities, program, start_date, end_date):
    """WHERE clause for the user's scope ceiling narrowed by the filter bar's
    own selections (district scope, facility, programme, date range)."""
    # DISABLED: see _ceiling_scope_where above.
    # parts = _scope_where_parts(
    #     level, location, selected_districts or None, user_districts, selected_facilities or None, None,
    #     programs=[program] if program else None,
    # )
    parts = []
    if start_date and end_date:
        parts.append(f"{DATE_} BETWEEN '{start_date}'::TIMESTAMP AND '{end_date} 23:59:59'::TIMESTAMP")
    return " AND ".join(parts) if parts else "1=1"


def _dq_prefs_path(route):
    return os.path.join(os.getcwd(), f'data/{route}', 'dcc_dropdown_json', 'dq_preferences.json')


def _load_dq_prefs(route, uuid):
    """Per-user Completeness rules (mandatory encounters + demographics),
    saved under data/{route}/dcc_dropdown_json/dq_preferences.json so they're
    already selected the next time this uuid opens the page."""
    empty = {"encounters": [], "demographics": []}
    if not uuid:
        return empty
    try:
        with open(_dq_prefs_path(route)) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return empty
    for entry in data.get("users", []):
        if entry.get("uuid") == uuid:
            return {
                "encounters": entry.get("encounters") or [],
                "demographics": entry.get("demographics") or [],
            }
    return empty


def _save_dq_prefs(route, uuid, encounters, demographics):
    if not uuid:
        return
    prefs_path = _dq_prefs_path(route)
    try:
        with open(prefs_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    users = data.setdefault("users", [])
    for entry in users:
        if entry.get("uuid") == uuid:
            entry["encounters"] = encounters or []
            entry["demographics"] = demographics or []
            break
    else:
        users.append({"uuid": uuid, "encounters": encounters or [], "demographics": demographics or []})
    os.makedirs(os.path.dirname(prefs_path), exist_ok=True)
    with open(prefs_path, 'w') as f:
        json.dump(data, f, indent=2)


def _presence_expr(col):
    return f'("{col}" IS NOT NULL AND trim(CAST("{col}" AS VARCHAR)) <> \'\')'


def _rule_fields_display(rid, other_fields):
    """D4 ("Other") has no fixed field set -- show whatever the user actually
    picked instead of DUP_RULES's static placeholder text."""
    if rid == "D4":
        if other_fields:
            label_map = dict(DUP_FIELD_OPTIONS)
            return " + ".join(label_map.get(f, f) for f in other_fields)
        return "no fields selected"
    return DUP_RULES[rid]["fields"]


def _tab_label_and_style(base_label, count):
    """Tab label/style pair showing an issue count directly on the tab
    itself (e.g. "Duplicates (2 issues)") -- dcc.Tab's label can only be
    plain text, so the whole label (not just the number) turns red when
    there's something to look at."""
    if count is None:
        return base_label, _TAB_STYLE
    if not count:
        return base_label, _TAB_STYLE
    label = f"{base_label} ({count} issue{'s' if count != 1 else ''})"
    return label, {**_TAB_STYLE, "color": "#DC2626", "fontWeight": 700}


def _kpi_card(label, value, sub=None):
    children = [
        html.Div(label, className="dq-kpi-label"),
        html.Div(value, className="dq-kpi-value"),
    ]
    if sub:
        children.append(html.Div(sub, className="dq-kpi-sub"))
    return html.Div(children, className="dq-kpi-card")


def _empty_state(title, body):
    return html.Div(
        [html.Div(title, className="dq-empty-state-title"), html.Div(body)],
        className="dq-empty-state",
    )


layout = html.Div(
    className="dq-page",
    children=[
        html.Div(
            className="dq-header-row",
            children=[
                # html.Div(
                #     className="dq-header-title-col",
                #     children=[html.H2("Data Quality", className="dq-page-title")],
                # ),
                html.Div(
                    id="dq-filter-bar",
                    className="dq-header-filters-col config-controls-grid",
                    children=[
                        html.Div(
                            className="config-control-group",
                            children=[
                                html.Label("Date Range", className="config-label"),
                                dcc.DatePickerRange(
                                    id="dq-date-range",
                                    display_format="YYYY-MM-DD",
                                    minimum_nights=0,
                                    className="modern-datepicker-range",
                                ),
                            ],
                        ),
                        html.Div(
                            className="config-control-group",
                            children=[
                                html.Label("Scope", className="config-label"),
                                dcc.Dropdown(
                                    id="dq-scope",
                                    options=[], value=[], multi=True, clearable=True,
                                    placeholder="All districts in scope",
                                    className="modern-dropdown",
                                ),
                            ],
                        ),
                        html.Div(
                            className="config-control-group",
                            children=[
                                html.Label("Health Facility", className="config-label"),
                                dcc.Dropdown(
                                    id="dq-facility-filter",
                                    options=[], value=[], multi=True, clearable=True,
                                    placeholder="All facilities in scope",
                                    className="modern-dropdown",
                                ),
                            ],
                        ),
                        html.Div(
                            className="config-control-group",
                            children=[
                                html.Label("Programme", className="config-label"),
                                dcc.Dropdown(
                                    id="dq-program-filter",
                                    options=[], value=None, multi=False, clearable=False,
                                    placeholder="Choose a programme…",
                                    className="modern-dropdown",
                                ),
                            ],
                        ),
                        html.Div(
                            className="config-control-group",
                            children=[
                                html.Label(" ", className="config-label"),
                                html.Button("Run DQ", id="dq-run-btn", n_clicks=0, className="dq-run-btn"),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        html.Div(id="dq-alert"),
        html.Div(
            id="dq-tabs-wrapper",
            children=[
                dcc.Tabs(
                    id="dq-tabs",
                    value="overview",
                    children=[
                        dcc.Tab(
                            label="Overview", value="overview",
                            style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE,
                            children=html.Div(id="dq-overview-content", className="results-card"),
                        ),
                        dcc.Tab(
                            id="dq-tab-duplicates",
                            label="Duplicates", value="duplicates",
                            style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE,
                            children=html.Div(
                                className="results-card",
                                children=[
                                    html.Div(
                                        className="dq-panel",
                                        children=[
                                            html.H4("Matching rules", className="dq-panel-title"),
                                            dcc.Checklist(
                                                id="dq-dup-rules",
                                                options=[
                                                    {
                                                        "label": f"{rid} — {DUP_RULES[rid]['label']} "
                                                                 f"({DUP_RULES[rid]['confidence']:.2f})",
                                                        "value": rid,
                                                    }
                                                    for rid in DUP_RULE_ORDER
                                                ],
                                                value=["D1", "D2", "D3"],
                                                className="dq-checklist-row",
                                                labelClassName="dq-checklist-label",
                                                inputStyle={"marginRight": "6px"},
                                            ),
                                            html.Div(
                                                id="dq-dup-other-fields-group",
                                                className="config-control-group",
                                                style={"marginTop": "12px", "display": "none"},
                                                children=[
                                                    html.Label(
                                                        "D4 (Other) fields",
                                                        className="config-label",
                                                    ),
                                                    dcc.Dropdown(
                                                        id="dq-dup-other-fields",
                                                        options=[
                                                            {"label": label, "value": value}
                                                            for value, label in DUP_FIELD_OPTIONS
                                                        ],
                                                        value=[], multi=True, clearable=True,
                                                        placeholder="Choose fields to match on…",
                                                        className="modern-dropdown",
                                                    ),
                                                ],
                                            ),
                                            html.Label(
                                                "Minimum confidence to show",
                                                className="config-label",
                                                style={"marginTop": "12px", "display": "block"},
                                            ),
                                            dcc.Slider(
                                                id="dq-dup-min-confidence",
                                                min=0, max=1, step=0.01, value=0,
                                                marks={0: "0", 0.25: "0.25", 0.5: "0.5", 0.75: "0.75", 1: "1"},
                                                tooltip={"placement": "bottom", "always_visible": False},
                                            ),
                                        ],
                                    ),
                                    dcc.Store(id="dq-dup-candidates-page", data=1),
                                    html.Div(id="dq-duplicates-content"),
                                ],
                            ),
                        ),
                        dcc.Tab(
                            id="dq-tab-completeness",
                            label="Completeness", value="completeness",
                            style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE,
                            children=html.Div(
                                className="results-card",
                                children=[
                                    html.Div(
                                        className="dq-panel",
                                        children=[
                                            html.H4("Completeness rules", className="dq-panel-title"),
                                            html.Div(
                                                className="config-controls-grid",
                                                children=[
                                                    html.Div(
                                                        className="config-control-group",
                                                        children=[
                                                            html.Label(
                                                                "Mandatory Demographics",
                                                                className="config-label",
                                                            ),
                                                            dcc.Dropdown(
                                                                id="dq-completeness-demographics",
                                                                options=[
                                                                    {"label": label, "value": value}
                                                                    for value, label in DEMOGRAPHIC_FIELD_OPTIONS
                                                                ],
                                                                value=[], multi=True, clearable=True,
                                                                placeholder="Select required demographic fields…",
                                                                className="modern-dropdown",
                                                            ),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        className="config-control-group",
                                                        children=[
                                                            html.Label(
                                                                "Mandatory Encounters",
                                                                className="config-label",
                                                            ),
                                                            dcc.Dropdown(
                                                                id="dq-completeness-encounters",
                                                                options=[], value=[], multi=True, clearable=True,
                                                                placeholder="Select required encounters…",
                                                                className="modern-dropdown",
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                "A person record is complete when every selected demographic "
                                                "field is filled in and the person has at least one record "
                                                "under each selected encounter. Encounter options reflect the "
                                                "selected programme's last 7 days of activity. Your selection "
                                                "is remembered for next time.",
                                                className="dq-panel-note",
                                            ),
                                        ],
                                    ),
                                    html.Div(id="dq-prefs-save-status", style={"display": "none"}),
                                    html.Div(id="dq-completeness-content", className="card-2"),
                                ],
                            ),
                        ),
                        dcc.Tab(
                            label="Validity and outliers", value="validity",
                            style=_TAB_STYLE, selected_style=_TAB_SELECTED_STYLE,
                            children=html.Div(id="dq-validity-content", className="card-2"),
                        ),
                    ],
                ),
            ],
        ),
    ],
)


@callback(
    Output("dq-alert", "children"),
    Output("dq-filter-bar", "style"),
    Output("dq-tabs-wrapper", "style"),
    Output("dq-scope", "options"),
    Output("dq-scope", "value"),
    Output("dq-scope", "disabled"),
    Output("dq-facility-filter", "options"),
    Output("dq-facility-filter", "value"),
    Output("dq-facility-filter", "disabled"),
    Output("dq-program-filter", "options"),
    Output("dq-program-filter", "value"),
    Output("dq-date-range", "start_date"),
    Output("dq-date-range", "end_date"),
    Output("dq-date-range", "min_date_allowed"),
    Output("dq-date-range", "max_date_allowed"),
    Input("url-params-store", "data"),
)
def initialize_data_quality_filters(urlparams):
    urlparams = urlparams or {}
    hidden = {"display": "none"}
    unauthorized = (
        html.Div("Unauthorized user. Please contact your system administrator.", className="dq-status-message"),
        hidden, hidden,
        [], [], True,
        [], [], True,
        [], None,
        None, None, None, None,
    )

    data_route = urlparams.get("route", ["default"])[0]
    location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]

    # DISABLED: _load_user_registry/_resolve_user_scope are from pages.home --
    # see the commented import at the top of this file. Falls back to
    # "unauthorized" (user_row=None), which every call site below already
    # checks for and handles safely.
    # user_data = _load_user_registry(data_route)
    # user_row, scope = _resolve_user_scope(urlparams, user_data)
    user_row, scope = None, {}
    if user_row is None:
        return unauthorized

    if not location:
        return (
            html.Div("Missing Location parameter.", className="dq-status-message"),
            hidden, hidden,
            [], [], True,
            [], [], True,
            [], None,
            None, None, None, None,
        )

    data_path = f"data/{data_route}/parquet"
    level = scope.get("level")
    user_districts = scope.get("districts") or []
    if isinstance(user_districts, str):
        user_districts = [user_districts]

    ceiling_where = _ceiling_scope_where(level, location, user_districts)

    try:
        dist_df = DataStorage.query_duckdb(
            f"SELECT DISTINCT {DISTRICT_} FROM '{data_path}' WHERE {ceiling_where} ORDER BY {DISTRICT_}"
        )
        district_options = dist_df[DISTRICT_].dropna().tolist()
    except Exception:
        district_options = []

    try:
        fac_df = DataStorage.query_duckdb(
            f"SELECT DISTINCT {FACILITY_} FROM '{data_path}' WHERE {ceiling_where} ORDER BY {FACILITY_}"
        )
        facility_options = fac_df[FACILITY_].dropna().tolist()
    except Exception:
        facility_options = []

    try:
        prog_df = DataStorage.query_duckdb(
            f"SELECT {PROGRAM_}, COUNT(*) AS n FROM '{data_path}' WHERE {ceiling_where} "
            f"GROUP BY {PROGRAM_} ORDER BY n DESC"
        )
        program_options = prog_df[PROGRAM_].dropna().tolist()
        default_program = program_options[0] if program_options else None
    except Exception:
        program_options, default_program = [], None

    try:
        bounds_df = DataStorage.query_duckdb(f"SELECT MIN({DATE_}) AS min_d, MAX({DATE_}) AS max_d FROM '{data_path}'")
        min_date, max_date = bounds_df["min_d"][0], bounds_df["max_d"][0]
    except Exception:
        min_date, max_date = None, None

    start_date, end_date = _latest_full_month_window(max_date)

    # A district- or facility-level user is already ceilinged to their own
    # district(s) -- Scope has nothing left to narrow, so it's locked to
    # exactly what the ceiling query returned. Only a national-level user
    # picks among more than one district.
    district_disabled = level in ("district", "facility")
    district_value = district_options if district_disabled else []

    facility_disabled = level == "facility"
    facility_value = facility_options if facility_disabled else []

    return (
        None, {}, {},
        [{"label": d, "value": d} for d in district_options], district_value, district_disabled,
        [{"label": f, "value": f} for f in facility_options], facility_value, facility_disabled,
        [{"label": p, "value": p} for p in program_options], default_program,
        start_date, end_date, _iso_date(min_date), _iso_date(max_date),
    )


@callback(
    Output("dq-facility-filter", "options", allow_duplicate=True),
    Output("dq-facility-filter", "value", allow_duplicate=True),
    Input("dq-scope", "value"),
    State("url-params-store", "data"),
    prevent_initial_call=True,
)
def sync_dq_facility_options_from_scope(selected_districts, urlparams):
    """Narrows the Health Facility dropdown's options to whichever
    district(s) are picked in Scope -- mirrors the ceiling-ordered query
    initialize_data_quality_filters runs, just with the Scope selection
    folded into the WHERE clause instead of left out of it."""
    urlparams = urlparams or {}
    data_route = urlparams.get("route", ["default"])[0]
    location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]

    # DISABLED: _load_user_registry/_resolve_user_scope are from pages.home --
    # see the commented import at the top of this file. Falls back to
    # "unauthorized" (user_row=None), which every call site below already
    # checks for and handles safely.
    # user_data = _load_user_registry(data_route)
    # user_row, scope = _resolve_user_scope(urlparams, user_data)
    user_row, scope = None, {}
    if user_row is None or not location:
        raise PreventUpdate

    level = scope.get("level")
    if level == "facility":
        # Already ceilinged to a single facility -- Scope is disabled and
        # dq-facility-filter is already fixed by initialize_data_quality_filters.
        raise PreventUpdate

    user_districts = scope.get("districts") or []
    if isinstance(user_districts, str):
        user_districts = [user_districts]

    data_path = f"data/{data_route}/parquet"
    # DISABLED: _scope_where_parts is from pages.home -- see the commented
    # import at the top of this file. Falls back to no scope restriction.
    # where_parts = _scope_where_parts(level, location, selected_districts or None, user_districts, None, None)
    where_parts = []
    where = " AND ".join(where_parts) if where_parts else "1=1"

    try:
        fac_df = DataStorage.query_duckdb(
            f"SELECT DISTINCT {FACILITY_} FROM '{data_path}' WHERE {where} ORDER BY {FACILITY_}"
        )
        facility_options = fac_df[FACILITY_].dropna().tolist()
    except Exception:
        facility_options = []

    return [{"label": f, "value": f} for f in facility_options], []


@callback(
    Output("dq-overview-content", "children"),
    Input("url-params-store", "data"),
    Input("dq-run-btn", "n_clicks"),
    State("dq-date-range", "start_date"),
    State("dq-date-range", "end_date"),
    State("dq-scope", "value"),
    State("dq-facility-filter", "value"),
    State("dq-program-filter", "value"),
)
def render_overview_tab(urlparams, run_clicks, start_date, end_date, districts, facilities, program):
    urlparams = urlparams or {}
    data_route = urlparams.get("route", ["default"])[0]
    location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]

    # DISABLED: _load_user_registry/_resolve_user_scope are from pages.home --
    # see the commented import at the top of this file. Falls back to
    # "unauthorized" (user_row=None), which every call site below already
    # checks for and handles safely.
    # user_data = _load_user_registry(data_route)
    # user_row, scope = _resolve_user_scope(urlparams, user_data)
    user_row, scope = None, {}
    if user_row is None or not location:
        return None

    if not run_clicks:
        return _empty_state(
            "Click \"Run DQ\" to see results",
            "Set your filters above, then click Run DQ to compute this tab.",
        )

    if not program:
        return _empty_state(
            "Select a programme",
            "Every number on this tab is scoped to one programme at a time -- "
            "a patient is identified by programme, so there is nothing to compute without one.",
        )

    data_path = f"data/{data_route}/parquet"
    level = scope.get("level")
    user_districts = scope.get("districts") or []
    if isinstance(user_districts, str):
        user_districts = [user_districts]

    where = _selection_where(level, location, user_districts, districts, facilities, program, start_date, end_date)

    try:
        kpi_df = DataStorage.query_duckdb(
            f"SELECT COUNT(DISTINCT {PERSON_ID_}) AS patients, "
            f"COUNT(DISTINCT ({PERSON_ID_}, {CONCEPT_NAME_})) AS obs_rows "
            f"FROM '{data_path}' WHERE {where}"
        )
    except Exception:
        kpi_df = pd.DataFrame()

    if kpi_df.empty or int(kpi_df["obs_rows"][0]) == 0:
        return _empty_state(
            "No records match the current filters",
            "Try widening the date range, clearing the facility filter, or choosing a different programme.",
        )

    patients = int(kpi_df["patients"][0])
    obs_rows = int(kpi_df["obs_rows"][0])

    try:
        roster_df = DataStorage.query_duckdb(
            f"SELECT {PERSON_ID_} AS person_id, "
            f"MAX({LAST_NAME_}) AS family_name, MAX({FIRST_NAME_}) AS given_name, "
            f"MAX({GENDER_}) AS gender, MAX({BIRTHDATE_}) AS birthdate, "
            f"MAX({IDENTIFIER_}) AS identifier, MAX({VILLAGE_}) AS village, "
            f"MAX({TA_}) AS ta, MAX({HOME_DISTRICT_}) AS home_district, MAX({CELL_}) AS cell, "
            f"MAX({FACILITY_}) AS facility, COUNT(DISTINCT {ENCOUNTER_ID_}) AS encounter_count, "
            f"MIN({DATE_}) AS first_encounter, MAX({DATE_}) AS last_encounter "
            f"FROM '{data_path}' WHERE {where} GROUP BY {PERSON_ID_}"
        )
        duplicate_groups, _ = match_duplicates(roster_df, DUP_RULE_ORDER) if not roster_df.empty else ([], {})
    except Exception:
        duplicate_groups = []

    kpi_strip = html.Div(
        [
            _kpi_card("Patients in programme", f"{patients:,}"),
            _kpi_card("Observation rows", f"{obs_rows:,}"),
            _kpi_card("Duplicate groups", f"{len(duplicate_groups):,}"),
            _kpi_card("Records failing a rule", "—", "Needs the Validity tab"),
            _kpi_card("Patients with complete data", "—", "Needs a completeness definition"),
        ],
        className="dq-kpi-row",
    )

    try:
        vol_df = DataStorage.query_duckdb(
            f"SELECT DATE({DATE_}) AS d, COUNT(DISTINCT ({PERSON_ID_}, {CONCEPT_NAME_})) AS n "
            f"FROM '{data_path}' WHERE {where} GROUP BY d ORDER BY d"
        )
    except Exception:
        vol_df = pd.DataFrame(columns=["d", "n"])

    vol_fig = go.Figure(go.Bar(
        x=vol_df["d"], y=vol_df["n"],
        text=vol_df["n"], texttemplate="%{text:,}",
        textposition="inside", insidetextanchor="end",
    ))
    vol_fig.update_layout(template="dq", xaxis_title=None, yaxis_title="Observations")

    volume_panel = html.Div(
        [
            html.H4("Observations volume by day", className="dq-panel-title"),
            dcc.Graph(figure=vol_fig, config={"displayModeBar": False}),
        ],
        className="dq-panel",
    )

    try:
        fac_df = DataStorage.query_duckdb(
            f'SELECT {FACILITY_} AS "Facility", '
            f'COUNT(DISTINCT {PERSON_ID_}) AS "Patients", '
            f'COUNT(DISTINCT {ENCOUNTER_ID_}) AS "Encounters", '
            f'COUNT(DISTINCT ({PERSON_ID_}, {CONCEPT_NAME_})) AS "Rows" '
            f"FROM '{data_path}' WHERE {where} GROUP BY {FACILITY_} ORDER BY \"Patients\" DESC"
        )
    except Exception:
        fac_df = pd.DataFrame()

    if not fac_df.empty:
        fac_df["Field completeness %"] = "-"

        try:
            dup_roster_df = DataStorage.query_duckdb(
                f"SELECT {PERSON_ID_} AS person_id, {FACILITY_} AS facility_group, "
                f"MAX({LAST_NAME_}) AS family_name, MAX({FIRST_NAME_}) AS given_name, "
                f"MAX({GENDER_}) AS gender, MAX({BIRTHDATE_}) AS birthdate, "
                f"MAX({IDENTIFIER_}) AS identifier, MAX({VILLAGE_}) AS village, "
                f"MAX({TA_}) AS ta, MAX({HOME_DISTRICT_}) AS home_district, MAX({CELL_}) AS cell, "
                f"MAX({FACILITY_}) AS facility, COUNT(DISTINCT {ENCOUNTER_ID_}) AS encounter_count, "
                f"MIN({DATE_}) AS first_encounter, MAX({DATE_}) AS last_encounter "
                f"FROM '{data_path}' WHERE {where} GROUP BY {PERSON_ID_}, {FACILITY_}"
            )
        except Exception:
            dup_roster_df = pd.DataFrame()

        dup_group_counts = {}
        if not dup_roster_df.empty:
            for facility_name, sub_roster in dup_roster_df.groupby("facility_group"):
                groups, _ = match_duplicates(sub_roster, DUP_RULE_ORDER)
                dup_group_counts[facility_name] = len(groups)
        fac_df["Duplicate groups"] = fac_df["Facility"].map(dup_group_counts).fillna(0).astype(int)

        fac_df["% of Patients Completing Workflow"] = "-"

    scorecard_panel = html.Div(
        [
            html.H4("Facility scorecard", className="dq-panel-title"),
            html.Div(
                "Field completeness and % of Patients Completing Workflow are placeholders "
                "pending a definition; Duplicate groups matches this facility's own roster "
                "the same way the Duplicates tab does.",
                className="dq-panel-note",
            ),
            dash_table.DataTable(
                columns=[{"name": c, "id": c} for c in fac_df.columns],
                data=fac_df.to_dict("records"),
                page_size=15,
                sort_action="native",
            ) if not fac_df.empty else html.Div("No facility rows in scope.", className="dq-empty-state"),
        ],
        className="dq-panel",
    )

    deferred_panel = _empty_state(
        "Not yet available",
        html.Ul(
            [
                html.Li("Duplicate groups and the duplicate rate -- computed by the Duplicates tab."),
                html.Li("Records failing a rule and the defects table -- computed by the Validity tab's rule list."),
                html.Li("The five-dimension quality index -- needs signal from Duplicates, Completeness and Validity together."),
            ]
        ),
    )

    return html.Div([kpi_strip, volume_panel, scorecard_panel, deferred_panel])


_COMPARE_FIELDS = [
    ("given_name", "Given name"), ("family_name", "Family name"), ("gender", "Gender"),
    ("birthdate", "Birthdate"), ("identifier", "Identifier"), ("village", "Village"),
    ("ta", "TA"), ("home_district", "Home district"), ("cell", "Phone"),
    ("facility", "Facility"), ("encounter_count", "Encounters"),
    ("first_encounter", "First encounter"), ("last_encounter", "Last encounter"),
]


def _format_cell(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return str(value)


def _comparison_table(members_df):
    header = html.Tr([html.Th("Field")] + [html.Th(f"person_id {pid}") for pid in members_df["person_id"]])
    rows = []
    for col, label in _COMPARE_FIELDS:
        values = members_df[col].tolist()
        differs = len({_format_cell(v) for v in values}) > 1
        cells = [html.Td(label, className="dq-diff-field")]
        for v in values:
            cell_class = "dq-diff-cell dq-diff-cell-mismatch" if differs else "dq-diff-cell"
            cells.append(html.Td(_format_cell(v), className=cell_class))
        rows.append(html.Tr(cells))
    return html.Table([html.Thead(header), html.Tbody(rows)], className="dq-compare-table")


def _person_attributes_cell(best):
    fields = [
        ("Identifier", best.get("identifier")),
        ("Given Name", best.get("given_name")),
        ("Last Name", best.get("family_name")),
        ("Gender", best.get("gender")),
        ("Birthdate", best.get("birthdate")),
    ]
    return html.Div([html.Div(f"{label}: {_format_cell(value)}") for label, value in fields])


def _candidate_row(sn, group, roster_df):
    """One 'Candidate groups' table row -- SN, the representative person's
    attributes (most encounters, ties broken by obs_rows), an expandable
    'Similar Records' cell (native <details>/<summary>, same side-by-side
    comparison as before, just moved out of the summary line), Confidence,
    and Rules."""
    members_df = roster_df[roster_df["person_id"].isin(group["members"])].copy()
    best = members_df.sort_values(["encounter_count", "obs_rows"], ascending=False).iloc[0]
    keep_line = html.Div(
        f"A merge would keep person_id {best['person_id']} ({int(best['encounter_count'])} encounters) "
        f"and retire {len(members_df) - 1} record(s). Read-only -- no merge is performed.",
        className="dq-panel-note",
    )
    n = len(group["members"])
    similar_records = html.Details(
        [
            html.Summary(f"{n} Record{'s' if n != 1 else ''}", className="dq-group-summary"),
            _comparison_table(members_df),
            keep_line,
        ],
        className="dq-group-details",
    )
    return html.Tr([
        html.Td(str(sn)),
        html.Td(_person_attributes_cell(best)),
        html.Td(similar_records),
        html.Td(f"{group['confidence']:.2f}"),
        html.Td(", ".join(group["rules"]) or "none"),
    ])


@callback(
    Output("dq-dup-other-fields-group", "style"),
    Input("dq-dup-rules", "value"),
)
def toggle_dup_other_fields(enabled_rules):
    base_style = {"marginTop": "12px"}
    if "D4" not in (enabled_rules or []):
        base_style["display"] = "none"
    return base_style


@callback(
    Output("dq-dup-candidates-page", "data"),
    Input("dq-run-btn", "n_clicks"),
)
def reset_candidates_page(_n_clicks):
    """A fresh "Run DQ" invalidates whatever page the user was on -- e.g. a
    stale page 5 could land past the end of a now-shorter candidate list."""
    return 1


@callback(
    Output("dq-dup-candidates-page", "data", allow_duplicate=True),
    Input("dq-candidates-prev-btn", "n_clicks"),
    State("dq-dup-candidates-page", "data"),
    prevent_initial_call=True,
)
def candidates_prev_page(_n_clicks, page):
    return max(1, (page or 1) - 1)


@callback(
    Output("dq-dup-candidates-page", "data", allow_duplicate=True),
    Input("dq-candidates-next-btn", "n_clicks"),
    State("dq-dup-candidates-page", "data"),
    prevent_initial_call=True,
)
def candidates_next_page(_n_clicks, page):
    return (page or 1) + 1


@callback(
    Output("dq-duplicates-content", "children"),
    Output("dq-tab-duplicates", "label"),
    Output("dq-tab-duplicates", "style"),
    Input("url-params-store", "data"),
    Input("dq-run-btn", "n_clicks"),
    Input("dq-dup-candidates-page", "data"),
    State("dq-date-range", "start_date"),
    State("dq-date-range", "end_date"),
    State("dq-scope", "value"),
    State("dq-facility-filter", "value"),
    State("dq-program-filter", "value"),
    State("dq-dup-rules", "value"),
    State("dq-dup-other-fields", "value"),
    State("dq-dup-min-confidence", "value"),
)
def render_duplicates_tab(urlparams, run_clicks, candidates_page, start_date, end_date, districts, facilities,
                           program, enabled_rules, other_fields, min_confidence):
    urlparams = urlparams or {}
    data_route = urlparams.get("route", ["default"])[0]
    location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]

    # DISABLED: _load_user_registry/_resolve_user_scope are from pages.home --
    # see the commented import at the top of this file. Falls back to
    # "unauthorized" (user_row=None), which every call site below already
    # checks for and handles safely.
    # user_data = _load_user_registry(data_route)
    # user_row, scope = _resolve_user_scope(urlparams, user_data)
    user_row, scope = None, {}
    if user_row is None or not location:
        return None, "Duplicates", _TAB_STYLE

    if not run_clicks:
        return (
            _empty_state(
                "Click \"Run DQ\" to see results",
                "Set your filters above, then click Run DQ to compute this tab.",
            ),
            "Duplicates", _TAB_STYLE,
        )

    if not program:
        return (
            _empty_state(
                "Select a programme",
                "Duplicate matching is scoped to one programme's patient roster at a time.",
            ),
            "Duplicates", _TAB_STYLE,
        )

    data_path = f"data/{data_route}/parquet"
    level = scope.get("level")
    user_districts = scope.get("districts") or []
    if isinstance(user_districts, str):
        user_districts = [user_districts]

    where = _selection_where(level, location, user_districts, districts, facilities, program, start_date, end_date)
    # Identifier integrity is checked across the whole scoped extract, not
    # just the selected programme -- same scope, no Program filter.
    scope_where = _selection_where(level, location, user_districts, districts, facilities, None, start_date, end_date)

    try:
        roster_df = DataStorage.query_duckdb(
            f"SELECT {PERSON_ID_} AS person_id, "
            f"MAX({LAST_NAME_}) AS family_name, MAX({FIRST_NAME_}) AS given_name, "
            f"MAX({GENDER_}) AS gender, MAX({BIRTHDATE_}) AS birthdate, "
            f"MAX({IDENTIFIER_}) AS identifier, MAX({VILLAGE_}) AS village, "
            f"MAX({TA_}) AS ta, MAX({HOME_DISTRICT_}) AS home_district, MAX({CELL_}) AS cell, "
            f"MAX({FACILITY_}) AS facility, COUNT(DISTINCT {ENCOUNTER_ID_}) AS encounter_count, "
            f"COUNT(DISTINCT ({PERSON_ID_}, {CONCEPT_NAME_})) AS obs_rows, "
            f"MIN({DATE_}) AS first_encounter, MAX({DATE_}) AS last_encounter "
            f"FROM '{data_path}' WHERE {where} GROUP BY {PERSON_ID_}"
        )
    except Exception:
        roster_df = pd.DataFrame()

    if roster_df.empty:
        return (
            _empty_state(
                "No records match the current filters",
                "Try widening the date range, clearing the facility filter, or choosing a different programme.",
            ),
            "Duplicates", _TAB_STYLE,
        )

    enabled_rules = enabled_rules or []
    groups, per_rule_counts = match_duplicates(roster_df, enabled_rules, other_fields=other_fields)

    patient_records = len(roster_df)
    surplus = sum(len(g["members"]) - 1 for g in groups)
    distinct_identities = patient_records - surplus
    records_involved = sum(len(g["members"]) for g in groups)
    duplicate_rate = (surplus / patient_records * 100) if patient_records else 0.0

    summary_strip = html.Div(
        [
            _kpi_card("Patient records", f"{patient_records:,}"),
            _kpi_card("Duplicate Groups", f"{len(groups):,}"),
            _kpi_card("Distinct Patients if Merged", f"{distinct_identities:,}"),
            _kpi_card("Records Affected", f"{records_involved:,}"),
            _kpi_card("Duplicate rate", f"{duplicate_rate:.1f}%", "surplus ÷ patient records"),
        ],
        className="dq-kpi-row",
    )

    per_rule_table = dash_table.DataTable(
        columns=[
            {"name": "Rule", "id": "rule"}, {"name": "Key", "id": "key"},
            {"name": "Confidence", "id": "confidence"},
            {"name": "Groups", "id": "groups"}, {"name": "Records", "id": "records"},
        ],
        data=[
            {
                "rule": f"{rid} — {DUP_RULES[rid]['label']}",
                "key": _rule_fields_display(rid, other_fields),
                "confidence": f"{DUP_RULES[rid]['confidence']:.2f}",
                "groups": per_rule_counts[rid]["groups"],
                "records": per_rule_counts[rid]["records"],
            }
            for rid in DUP_RULE_ORDER
        ],
        page_size=6,
    )

    if records_involved:
        involved_ids = {pid for g in groups for pid in g["members"]}
        by_facility = (
            roster_df[roster_df["person_id"].isin(involved_ids)]
            .groupby("facility")["person_id"].nunique()
            .reset_index(name="records_involved")
            .sort_values("records_involved", ascending=False)
        )
        facility_table = dash_table.DataTable(
            columns=[{"name": "Facility", "id": "facility"}, {"name": "Records involved", "id": "records_involved"}],
            data=by_facility.to_dict("records"),
            page_size=10, sort_action="native",
        )
    else:
        facility_table = html.Div("No duplicate records to break down by facility.", className="dq-empty-state")

    try:
        ident_shared = DataStorage.query_duckdb(
            f"SELECT COUNT(*) AS n FROM (SELECT {IDENTIFIER_} FROM '{data_path}' "
            f"WHERE {scope_where} AND {_presence_expr(IDENTIFIER_)} "
            f"GROUP BY {IDENTIFIER_} HAVING COUNT(DISTINCT {PERSON_ID_}) > 1)"
        )["n"][0]
        ident_multi = DataStorage.query_duckdb(
            f"SELECT COUNT(*) AS n FROM (SELECT {PERSON_ID_} FROM '{data_path}' "
            f"WHERE {scope_where} AND {_presence_expr(IDENTIFIER_)} "
            f"GROUP BY {PERSON_ID_} HAVING COUNT(DISTINCT {IDENTIFIER_}) > 1)"
        )["n"][0]
        multi_program = DataStorage.query_duckdb(
            f"SELECT COUNT(*) AS n FROM (SELECT {PERSON_ID_} FROM '{data_path}' "
            f"WHERE {scope_where} GROUP BY {PERSON_ID_} HAVING COUNT(DISTINCT {PROGRAM_}) > 1)"
        )["n"][0]
    except Exception:
        ident_shared = ident_multi = multi_program = 0

    identity_panel = html.Div(
        [
            html.H4("Identifier integrity", className="dq-panel-title"),
            html.Div(
                "Checked across the whole scoped extract, not just the selected programme.",
                className="dq-panel-note",
            ),
            html.Div(
                [
                    _kpi_card("Identifiers shared by >1 person_id", f"{int(ident_shared):,}"),
                    _kpi_card("person_ids with >1 identifier", f"{int(ident_multi):,}"),
                    _kpi_card("Persons enrolled in >1 programme", f"{int(multi_program):,}"),
                ],
                className="dq-kpi-row",
            ),
        ],
        className="dq-panel",
    )

    min_confidence = min_confidence or 0
    candidate_groups = [g for g in groups if g["confidence"] >= min_confidence]
    candidates_pagination = None
    if not enabled_rules:
        candidates_panel = _empty_state(
            "No matching rule is switched on",
            "Turn on at least one rule above to compute duplicate groups.",
        )
    elif not candidate_groups:
        candidates_panel = _empty_state(
            "No candidate groups at this confidence",
            "Lower the minimum-confidence slider, or switch on more rules.",
        )
    else:
        total_pages = math.ceil(len(candidate_groups) / _CANDIDATES_PAGE_SIZE)
        page = max(1, min(candidates_page or 1, total_pages))
        start = (page - 1) * _CANDIDATES_PAGE_SIZE
        page_groups = candidate_groups[start:start + _CANDIDATES_PAGE_SIZE]

        candidates_panel = html.Table(
            [
                html.Thead(html.Tr([
                    html.Th("SN"), html.Th("Person Attributes"), html.Th("Similar Records"),
                    html.Th("Confidence"), html.Th("Rules"),
                ])),
                html.Tbody([
                    _candidate_row(sn, g, roster_df)
                    for sn, g in enumerate(page_groups, start=start + 1)
                ]),
            ],
            className="dq-candidates-table",
        )
        candidates_pagination = html.Div(
            [
                html.Button("Previous", id="dq-candidates-prev-btn", n_clicks=0,
                            disabled=page <= 1, className="dq-pagination-btn"),
                html.Span(f"Page {page} of {total_pages} ({len(candidate_groups):,} candidate groups)",
                          className="dq-pagination-info"),
                html.Button("Next", id="dq-candidates-next-btn", n_clicks=0,
                            disabled=page >= total_pages, className="dq-pagination-btn"),
            ],
            className="dq-pagination-row",
        )

    content = html.Div(
        [
            summary_strip,
            html.Div(
                [html.H4("Per-rule breakdown", className="dq-panel-title"), per_rule_table],
                className="dq-panel",
            ),
            html.Div(
                [html.H4("Duplicates by facility", className="dq-panel-title"), facility_table],
                className="dq-panel",
            ),
            html.Div(
                [
                    html.H4("Candidate groups", className="dq-panel-title"),
                    html.Div(
                        "Read-only. Person Attributes reflects the record with the most "
                        "encounters (ties broken by observation rows); expand Similar Records "
                        "for a field-by-field comparison, where differing fields are highlighted.",
                        className="dq-panel-note",
                    ),
                    candidates_panel,
                    candidates_pagination,
                ],
                className="dq-panel",
            ),
            identity_panel,
        ]
    )
    label, style = _tab_label_and_style("Duplicates", len(candidate_groups))
    return content, label, style


@callback(
    Output("dq-completeness-encounters", "options"),
    Input("dq-program-filter", "value"),
    Input("url-params-store", "data"),
)
def load_completeness_encounter_options(program, urlparams):
    if not program:
        return []
    urlparams = urlparams or {}
    data_route = urlparams.get("route", ["default"])[0]
    data_path = f"data/{data_route}/parquet"
    safe_program = str(program).replace("'", "''")
    try:
        enc_df = DataStorage.query_duckdb(
            f"SELECT DISTINCT {ENCOUNTER_} FROM '{data_path}' "
            f"WHERE {PROGRAM_} = '{safe_program}' "
            f"AND {DATE_} >= (SELECT MAX({DATE_}) FROM '{data_path}') - INTERVAL 7 DAY "
            f"ORDER BY {ENCOUNTER_}"
        )
        encounters = enc_df[ENCOUNTER_].dropna().tolist()
    except Exception:
        encounters = []
    return [{"label": e, "value": e} for e in encounters]


@callback(
    Output("dq-completeness-demographics", "value"),
    Output("dq-completeness-encounters", "value"),
    Input("url-params-store", "data"),
)
def load_dq_preferences(urlparams):
    """Restores this uuid's last saved Completeness rules -- demographics
    default to every field the first time a user opens the page (see
    DEMOGRAPHIC_FIELD_OPTIONS), encounters default to none since they're
    programme-specific and there's no universally sensible default."""
    urlparams = urlparams or {}
    data_route = urlparams.get("route", ["default"])[0]
    uuid = (urlparams.get("uuid") or [None])[0]
    prefs = _load_dq_prefs(data_route, uuid)
    demographics = prefs["demographics"] or [col for col, _ in DEMOGRAPHIC_FIELD_OPTIONS]
    return demographics, prefs["encounters"]


@callback(
    Output("dq-prefs-save-status", "children"),
    Input("dq-completeness-demographics", "value"),
    Input("dq-completeness-encounters", "value"),
    State("url-params-store", "data"),
    prevent_initial_call=True,
)
def save_dq_preferences(demographics, encounters, urlparams):
    urlparams = urlparams or {}
    data_route = urlparams.get("route", ["default"])[0]
    uuid = (urlparams.get("uuid") or [None])[0]
    _save_dq_prefs(data_route, uuid, encounters, demographics)
    return ""


@callback(
    Output("dq-completeness-content", "children"),
    Output("dq-tab-completeness", "label"),
    Output("dq-tab-completeness", "style"),
    Input("url-params-store", "data"),
    Input("dq-run-btn", "n_clicks"),
    State("dq-date-range", "start_date"),
    State("dq-date-range", "end_date"),
    State("dq-scope", "value"),
    State("dq-facility-filter", "value"),
    State("dq-program-filter", "value"),
    State("dq-completeness-demographics", "value"),
    State("dq-completeness-encounters", "value"),
)
def render_completeness_tab(urlparams, run_clicks, start_date, end_date, districts, facilities, program,
                             mandatory_demographics, mandatory_encounters):
    urlparams = urlparams or {}
    data_route = urlparams.get("route", ["default"])[0]
    location = (urlparams.get("Location") or urlparams.get("?Location") or [None])[0]

    # DISABLED: _load_user_registry/_resolve_user_scope are from pages.home --
    # see the commented import at the top of this file. Falls back to
    # "unauthorized" (user_row=None), which every call site below already
    # checks for and handles safely.
    # user_data = _load_user_registry(data_route)
    # user_row, scope = _resolve_user_scope(urlparams, user_data)
    user_row, scope = None, {}
    if user_row is None or not location:
        return None, "Completeness", _TAB_STYLE

    if not run_clicks:
        return (
            _empty_state(
                "Click \"Run DQ\" to see results",
                "Set your filters above, then click Run DQ to compute this tab.",
            ),
            "Completeness", _TAB_STYLE,
        )

    if not program:
        return (
            _empty_state(
                "Select a programme",
                "Completeness rules are evaluated against one programme's patient roster at a time.",
            ),
            "Completeness", _TAB_STYLE,
        )

    mandatory_demographics = mandatory_demographics or []
    mandatory_encounters = mandatory_encounters or []
    if not mandatory_demographics and not mandatory_encounters:
        return (
            _empty_state(
                "No completeness rule is set",
                "Pick at least one mandatory demographic field or encounter above.",
            ),
            "Completeness", _TAB_STYLE,
        )

    data_path = f"data/{data_route}/parquet"
    level = scope.get("level")
    user_districts = scope.get("districts") or []
    if isinstance(user_districts, str):
        user_districts = [user_districts]

    where = _selection_where(level, location, user_districts, districts, facilities, program, start_date, end_date)

    demo_flag_cols = [f"demo_{i}" for i in range(len(mandatory_demographics))]
    enc_flag_cols = [f"enc_{i}" for i in range(len(mandatory_encounters))]

    select_parts = [
        f"{PERSON_ID_} AS person_id",
        f"MAX({FACILITY_}) AS facility",
        f"MAX({IDENTIFIER_}) AS identifier",
        f"MAX({FIRST_NAME_}) AS given_name",
        f"MAX({LAST_NAME_}) AS family_name",
    ]
    for col, flag in zip(mandatory_demographics, demo_flag_cols):
        select_parts.append(f"MAX(CASE WHEN {_presence_expr(col)} THEN 1 ELSE 0 END) AS {flag}")
    for enc, flag in zip(mandatory_encounters, enc_flag_cols):
        safe_enc = str(enc).replace("'", "''")
        select_parts.append(f"MAX(CASE WHEN {ENCOUNTER_} = '{safe_enc}' THEN 1 ELSE 0 END) AS {flag}")

    try:
        df = DataStorage.query_duckdb(
            f"SELECT {', '.join(select_parts)} FROM '{data_path}' WHERE {where} GROUP BY {PERSON_ID_}"
        )
    except Exception:
        df = pd.DataFrame()

    if df.empty:
        return (
            _empty_state(
                "No records match the current filters",
                "Try widening the date range, clearing the facility filter, or choosing a different programme.",
            ),
            "Completeness", _TAB_STYLE,
        )

    demo_label_map = dict(DEMOGRAPHIC_FIELD_OPTIONS)
    df["demographics_complete"] = df[demo_flag_cols].eq(1).all(axis=1) if demo_flag_cols else True
    df["encounters_complete"] = df[enc_flag_cols].eq(1).all(axis=1) if enc_flag_cols else True
    df["is_complete"] = df["demographics_complete"] & df["encounters_complete"]

    total_patients = len(df)
    complete_count = int(df["is_complete"].sum())
    incomplete_count = total_patients - complete_count
    completeness_rate = (complete_count / total_patients * 100) if total_patients else 0.0

    metrics_strip = html.Div(
        [
            _kpi_card("Patients evaluated", f"{total_patients:,}"),
            _kpi_card("Complete records", f"{complete_count:,}"),
            _kpi_card("Incomplete records", f"{incomplete_count:,}"),
            _kpi_card("Completeness rate", f"{completeness_rate:.1f}%"),
        ],
        className="dq-kpi-row",
    )

    facility_summary = (
        df.groupby("facility")
        .agg(Patients=("person_id", "count"), Complete=("is_complete", "sum"))
        .reset_index()
        .rename(columns={"facility": "Facility"})
    )
    facility_summary["Incomplete"] = facility_summary["Patients"] - facility_summary["Complete"]
    facility_summary["Completeness %"] = (facility_summary["Complete"] / facility_summary["Patients"] * 100).round(1)
    facility_summary = facility_summary.sort_values("Completeness %")

    facility_table = dash_table.DataTable(
        columns=[{"name": c, "id": c} for c in ["Facility", "Patients", "Complete", "Incomplete", "Completeness %"]],
        data=facility_summary.to_dict("records"),
        page_size=15,
        sort_action="native",
    )

    def _missing(row, cols, flags, label_fn):
        missing = [label_fn(c) for c, f in zip(cols, flags) if row[f] == 0]
        return ", ".join(missing) if missing else "—"

    incomplete_df = df[~df["is_complete"]].copy()
    if not incomplete_df.empty:
        incomplete_df["Missing Demographics"] = incomplete_df.apply(
            lambda r: _missing(r, mandatory_demographics, demo_flag_cols, lambda c: demo_label_map.get(c, c)), axis=1
        )
        incomplete_df["Missing Encounters"] = incomplete_df.apply(
            lambda r: _missing(r, mandatory_encounters, enc_flag_cols, lambda e: e), axis=1
        )
        incomplete_df = incomplete_df.rename(columns={
            "identifier": "Identifier", "facility": "Facility",
            "given_name": "Given Name", "family_name": "Family Name",
        })
        display_cols = ["Identifier", "Facility", "Given Name", "Family Name", "Missing Demographics", "Missing Encounters"]
        incomplete_table = dash_table.DataTable(
            columns=[{"name": c, "id": c} for c in display_cols],
            data=incomplete_df[display_cols].to_dict("records"),
            page_size=15,
            sort_action="native",
        )
    else:
        incomplete_table = html.Div("No incomplete patient records at this scope.", className="dq-empty-state")

    content = html.Div(
        [
            metrics_strip,
            html.Div(
                [html.H4("Completeness by facility", className="dq-panel-title"), facility_table],
                className="dq-panel",
            ),
            html.Div(
                [
                    html.H4("Incomplete patient records", className="dq-panel-title"),
                    html.Div(
                        "Patients missing at least one mandatory demographic field or encounter.",
                        className="dq-panel-note",
                    ),
                    incomplete_table,
                ],
                className="dq-panel",
            ),
        ]
    )
    label, style = _tab_label_and_style("Completeness", incomplete_count)
    return content, label, style
