"""Executive Country Profile and Operational Readiness views for MNID."""
from __future__ import annotations

import dash_mantine_components as dmc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from mnid.charts.chart_helpers import _cov, _moving_average_values, _grouped_filter_counts
from mnid.charts.chart_helpers import (
    CHART_HEIGHT_MD, CHART_HEIGHT_LG,
    _graph_style, _graph_scroll_wrap, _clamp_chart_height,
)
from mnid.components.run_charts import (
    _EXEC_CHART_LAYOUT,
    _chart_key_slug,
    _trend_chart_payload,
)
from mnid.core.constants import BG, BORDER, DIM, FONT, GRID_C, MUTED, OK_C, TEXT, WARN_C
from mnid.aggregation.store import (
    get_aggregate as _get_aggregate,
    query_coverage as _agg_coverage,
    query_time_series as _agg_time_series,
)
from mnid.core.cache import _resolve_scope_filters

PRIMARY_GREEN = "#15803D"
SUCCESS_GREEN = "#16A34A"
LIGHT_GREEN = "#DCFCE7"
SOFT_GREEN = "#F0FDF4"
SOFT_BACKGROUND = "#F8FAFC"
ADMISSIONS_BLUE = "#2563EB"
MORTALITY_ROSE = "#E11D48"
WARNING_AMBER = "#F59E0B"
NEONATAL_ORANGE = "#D97706"
STILLBIRTH_BLUE = "#0284C7"
HERO_NAVY = "#182136"

def _section_header(title: str) -> html.Div:
    return html.Div([
        html.Span(style={
            "width": "3px", "height": "12px", "background": "#16a34a",
            "borderRadius": "2px", "flexShrink": "0", "display": "inline-block",
        }),
        html.Span(title, style={
            "fontSize": "11px", "fontWeight": "700", "color": "#64748b",
            "textTransform": "uppercase", "letterSpacing": ".09em",
        }),
    ], style={"display": "flex", "alignItems": "center", "gap": "7px", "marginBottom": "12px", "marginTop": "8px"})


def _responsive_grid(children: list, min_width: str = "220px", gap: str = "16px", margin_bottom: str = "20px") -> html.Div:
    return html.Div(
        children,
        style={
            "display": "grid",
            "gridTemplateColumns": f"repeat(auto-fit, minmax({min_width}, 1fr))",
            "gap": gap,
            "marginBottom": margin_bottom,
        },
    )


def _two_column_chart_grid(children: list, gap: str = "18px", margin_bottom: str = "20px") -> html.Div:
    return html.Div(
        children,
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
            "gap": gap,
            "marginBottom": margin_bottom,
        },
    )


def _exec_alert_banner(maternal_deaths: int, mmr: float, neonatal_deaths: int, stillbirths: int) -> html.Div:
    items = []
    if maternal_deaths > 0:
        items.append(("Maternal deaths", maternal_deaths, f"MMR {mmr:.0f} per 100,000 live births"))
    if neonatal_deaths > 0:
        items.append(("Neonatal deaths", neonatal_deaths, "Recorded in the selected period"))
    if stillbirths > 0:
        items.append(("Stillbirths", stillbirths, "Recorded in the selected period"))
    if not items:
        return html.Div()

    return html.Div(
        style={
            "display": "flex", "alignItems": "flex-start", "gap": "12px",
            "background": "#FFF7ED", "border": "1px solid #FED7AA",
            "borderRadius": "10px", "padding": "10px 14px",
            "marginBottom": "20px",
        },
        children=[
            html.Div(style={
                "display": "flex", "flexDirection": "column",
                "alignItems": "center", "gap": "3px", "flexShrink": "0",
            }, children=[
                html.Div(style={
                    "width": "10px", "height": "10px", "borderRadius": "50%",
                    "background": "#EF4444",
                    "animation": "mnid-dot-blink 1.3s ease-in-out infinite",
                }),
                html.Span(f"{sum(c for _, c, _ in items)}", style={
                    "fontSize": "15px", "fontWeight": "800", "color": "#DC2626", "lineHeight": "1",
                }),
                html.Span("events", style={"fontSize": "8px", "color": "#9A3412", "lineHeight": "1"}),
            ]),
            html.Div(style={"width": "1px", "alignSelf": "stretch", "background": "#FED7AA", "flexShrink": "0"}),
            html.Div(style={"flex": "1", "minWidth": "0"}, children=[
                html.Div("Priority Alert", style={
                    "fontSize": "12px", "fontWeight": "800", "color": "#9A3412", "marginBottom": "4px",
                }),
                html.Div("Maternal, neonatal, or stillbirth deaths were recorded in this reporting window.", style={
                    "fontSize": "11px", "color": "#9A3412", "marginBottom": "8px",
                }),
                html.Div([
                    html.Div([
                        html.Span(label, style={"fontSize": "11px", "fontWeight": "700", "color": "#7C2D12"}),
                        html.Span(f"{count:,}", style={"fontSize": "18px", "fontWeight": "800", "color": "#991B1B"}),
                        html.Span(sub, style={"fontSize": "10px", "color": "#9A3412"}),
                    ], style={
                        "padding": "8px 10px", "borderRadius": "10px", "background": "#FFF",
                        "border": "1px solid #FED7AA", "minWidth": "160px", "flex": "1",
                    })
                    for label, count, sub in items
                ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"}),
            ]),
        ]
    )


DISTRICT_REGION_ZONE = {
    "Blantyre": ("Southern Region", "Blantyre Zone"),
    "Chikwawa": ("Southern Region", "Blantyre Zone"),
    "Nsanje": ("Southern Region", "Blantyre Zone"),
    "Mulanje": ("Southern Region", "Blantyre Zone"),
    "Thyolo": ("Southern Region", "Blantyre Zone"),
    "Phalombe": ("Southern Region", "Blantyre Zone"),
    "Zomba": ("Southern Region", "Zomba Zone"),
    "Balaka": ("Southern Region", "Zomba Zone"),
    "Mangochi": ("Southern Region", "Zomba Zone"),
    "Machinga": ("Southern Region", "Zomba Zone"),
    "Mwanza": ("Southern Region", "Zomba Zone"),
    "Neno": ("Southern Region", "Zomba Zone"),
    "Lilongwe": ("Central Region", "Lilongwe Zone"),
    "Dedza": ("Central Region", "Lilongwe Zone"),
    "Ntcheu": ("Central Region", "Lilongwe Zone"),
    "Salima": ("Central Region", "Lilongwe Zone"),
    "Dowa": ("Central Region", "Lilongwe Zone"),
    "Kasungu": ("Central Region", "Lilongwe Zone"),
    "Ntchisi": ("Central Region", "Lilongwe Zone"),
    "Mchinji": ("Central Region", "Lilongwe Zone"),
    "Mzimba": ("Northern Region", "Mzuzu Zone"),
    "Karonga": ("Northern Region", "Mzuzu Zone"),
    "Rumphi": ("Northern Region", "Mzuzu Zone"),
    "Nkhata Bay": ("Northern Region", "Mzuzu Zone"),
    "Likoma": ("Northern Region", "Mzuzu Zone"),
    "Chitipa": ("Northern Region", "Mzuzu Zone"),
}


def _safe_div(num: float, den: float, scale: float = 1.0) -> float:
    if not den:
        return 0.0
    return round((num / den) * scale, 1)


def _copy_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "Date" in out.columns:
        out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    return out


def _period_bounds(df: pd.DataFrame) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    if df is None or df.empty or "Date" not in df.columns:
        return None, None
    date_series = pd.to_datetime(df["Date"], errors="coerce").dropna()
    if date_series.empty:
        return None, None
    return date_series.min(), date_series.max()


def _prior_period_df(df: pd.DataFrame) -> pd.DataFrame:
    start, end = _period_bounds(df)
    if start is None or end is None:
        return pd.DataFrame()
    span_days = max((end.normalize() - start.normalize()).days + 1, 1)
    prev_end = start - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=span_days - 1)
    return df[(df["Date"] >= prev_start) & (df["Date"] <= prev_end)].copy()


def _yn_mask(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    return df[column].fillna("").astype(str).str.strip().str.lower().isin({"yes", "true", "1"})


def _contains_mask(df: pd.DataFrame, column: str, values: list[str]) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    wanted = {str(value).strip().lower() for value in values}
    return df[column].fillna("").astype(str).str.strip().str.lower().isin(wanted)


def _service_mask(df: pd.DataFrame, services: list[str]) -> pd.Series:
    if "Service_Area" not in df.columns:
        return pd.Series(False, index=df.index)
    return _contains_mask(df, "Service_Area", services)


def _unique_count(df: pd.DataFrame, mask: pd.Series, unique_col: str) -> int:
    if unique_col not in df.columns or df.empty:
        return 0
    subset = df.loc[mask, unique_col].dropna().astype(str)
    return int(subset.nunique())


def _hierarchy_scope(df: pd.DataFrame, scope_meta: dict | None, period_label: str) -> list[dict]:
    scope_meta = scope_meta or {}
    district_values = sorted({str(v) for v in scope_meta.get("selected_districts") or [] if v})
    facility_values = sorted({str(v) for v in scope_meta.get("selected_facilities") or [] if v})
    if not district_values and "District" in df.columns:
        district_values = sorted(df["District"].dropna().astype(str).unique().tolist())
    if not facility_values and "Facility" in df.columns and len(df):
        facility_values = sorted(df["Facility"].dropna().astype(str).unique().tolist())[:1]

    regions = []
    zones = []
    for district in district_values:
        region, zone = DISTRICT_REGION_ZONE.get(district, ("National", "All zones"))
        regions.append(region)
        zones.append(zone)

    return [
        {"label": "Period", "value": period_label},
        {"label": "Region", "value": ", ".join(sorted(set(regions))) if regions else "National"},
        {"label": "Zone", "value": ", ".join(sorted(set(zones))) if zones else "All zones"},
        {"label": "District", "value": ", ".join(district_values[:2]) + (f" +{len(district_values)-2}" if len(district_values) > 2 else "") if district_values else "All districts"},
        {"label": "Facility", "value": ", ".join(facility_values[:1]) + (f" +{len(facility_values)-1}" if len(facility_values) > 1 else "") if facility_values else "All facilities"},
    ]


def _profile_scope_name(scope_meta: dict | None) -> dict:
    """Derive the profile view's naming from the active LEVEL/district/facility scope.

    national -> Country Profile; a single district/facility -> that place's own
    profile; 2+ selected -> Multi-District/Multi-Facility. Falls back to the
    national wording if level/selection is missing or unrecognized.
    """
    scope_meta = scope_meta or {}
    level = scope_meta.get("level")
    districts = [str(d) for d in (scope_meta.get("selected_districts") or []) if d]
    facilities = [str(f) for f in (scope_meta.get("selected_facilities") or []) if f]

    if level == "facility" and facilities:
        if len(facilities) == 1:
            name = facilities[0]
            return {"eyebrow": f"{name} Profile", "tab_label": "Facility Profile",
                    "overview": f"{name} facility overview"}
        return {"eyebrow": "Multi-Facility Profile", "tab_label": "Multi-Facility",
                "overview": f"{len(facilities)} facilities overview"}

    if level == "district" and districts:
        if len(districts) == 1:
            name = districts[0]
            return {"eyebrow": f"{name} District Profile", "tab_label": "District Profile",
                    "overview": f"{name} district overview"}
        return {"eyebrow": "Multi-District Profile", "tab_label": "Multi-District",
                "overview": f"{len(districts)} districts overview"}

    return {"eyebrow": "Country Profile", "tab_label": "Country Profile",
            "overview": "Malawi national overview"}


def _metric_snapshot(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {
            "maternal_admissions": 0,
            "neonatal_admissions": 0,
            "live_births": 0,
            "total_births": 0,
            "fresh_stillbirths": 0,
            "macerated_stillbirths": 0,
            "maternal_deaths": 0,
            "neonatal_deaths": 0,
            "stillbirths": 0,
            "institutional_mmr": 0.0,
            "neonatal_mortality_rate": 0.0,
            "stillbirth_rate": 0.0,
            "fresh_stillbirth_pct": 0.0,
            "macerated_stillbirth_pct": 0.0,
            "completeness": 0.0,
        }

    encounter_col = "encounter_id" if "encounter_id" in df.columns else "person_id"

    maternal_mask = _service_mask(df, ["ANC", "Labour", "PNC"])
    newborn_mask = _service_mask(df, ["Newborn"])
    labour_mask = _service_mask(df, ["Labour"])
    live_birth_mask = (
        _contains_mask(df, "concept_name", ["Outcome of the delivery"])
        & _contains_mask(df, "obs_value_coded", ["Live birth", "Live births", "Alive"])
    )
    fresh_stillbirth_mask = (
        _contains_mask(df, "concept_name", ["Outcome of the delivery", "Status of baby", "Admission outcome"])
        & _contains_mask(df, "obs_value_coded", ["Fresh stillbirth", "Fresh still birth"])
    )
    macerated_stillbirth_mask = (
        _contains_mask(df, "concept_name", ["Outcome of the delivery", "Status of baby", "Admission outcome"])
        & _contains_mask(df, "obs_value_coded", ["Macerated stillbirth", "Macerated still birth"])
    )
    stillbirth_mask = _yn_mask(df, "mnid_labour_stillbirth") | (
        _contains_mask(df, "concept_name", ["Outcome of the delivery", "Status of baby", "Admission outcome"])
        & _contains_mask(df, "obs_value_coded", ["Stillbirth", "Fresh stillbirth", "Macerated stillbirth", "Fresh still birth", "Macerated still birth"])
    )
    maternal_death_mask = _yn_mask(df, "mnid_pnc_maternal_death") | (
        _contains_mask(df, "concept_name", ["Status of the mother"])
        & _contains_mask(df, "obs_value_coded", ["Dead", "Died", "Maternal death"])
    )
    neonatal_death_mask = (
        _contains_mask(df, "concept_name", ["Admission outcome", "Status of baby"])
        & _contains_mask(df, "obs_value_coded", ["Died", "Dead", "Death", "Neonatal death"])
    )

    maternal_admissions = _unique_count(df, maternal_mask, encounter_col)
    neonatal_admissions = _unique_count(df, newborn_mask, encounter_col)
    live_births = _unique_count(df, live_birth_mask, "person_id")
    fresh_stillbirths = _unique_count(df, fresh_stillbirth_mask, "person_id")
    macerated_stillbirths = _unique_count(df, macerated_stillbirth_mask, "person_id")
    stillbirths = _unique_count(df, stillbirth_mask, "person_id")
    total_births = live_births + stillbirths
    maternal_deaths = _unique_count(df, maternal_death_mask, "person_id")
    neonatal_deaths = _unique_count(df, neonatal_death_mask, "person_id")

    completeness = 0.0
    if "concept_name" in df.columns:
        completeness = round(df["concept_name"].fillna("").astype(str).str.strip().ne("").mean() * 100, 1)

    return {
        "maternal_admissions": maternal_admissions,
        "neonatal_admissions": neonatal_admissions,
        "live_births": live_births,
        "total_births": total_births,
        "fresh_stillbirths": fresh_stillbirths,
        "macerated_stillbirths": macerated_stillbirths,
        "maternal_deaths": maternal_deaths,
        "neonatal_deaths": neonatal_deaths,
        "stillbirths": stillbirths,
        "institutional_mmr": _safe_div(maternal_deaths, live_births, 100000),
        "neonatal_mortality_rate": _safe_div(neonatal_deaths, live_births, 1000),
        "stillbirth_rate": _safe_div(stillbirths, total_births, 1000),
        "fresh_stillbirth_pct": _safe_div(fresh_stillbirths, stillbirths, 100),
        "macerated_stillbirth_pct": _safe_div(macerated_stillbirths, stillbirths, 100),
        "completeness": completeness,
    }


# DHIS2-native id for each _metric_snapshot count that has a real mapping
# (see mnid/dhis2/mnid_publish.py::DHIS2_TO_MNID_ID) -- completeness has no
# DHIS2 counterpart and stays None. maternal_admissions/neonatal_admissions
# are derived separately below (see _AGG_ADMISSION_IDS), not a 1:1 indicator.
_AGG_METRIC_IDS = {
    "total_births": "mnid_lab_core_totalbirths",
    "live_births": "mnid_lab_overview_004",
    "fresh_stillbirths": "mnid_lab_core_freshstillbirths",
    "macerated_stillbirths": "mnid_lab_core_maceratedstillbirths",
    "stillbirths": "mnid_lab_overview_005",
    "maternal_deaths": "mnid_pnc_overview_004",
    "neonatal_deaths": "mnid_nb_overview_002",
}

# Maternity Unit Admissions = clients enrolled under ANC + Labour + PNC;
# Neonatal Care Unit Admissions = clients under Newborn -- mirroring how
# _metric_snapshot defines these via _service_mask(df, [...]) for MAHIS.
# DHIS2 has no single "admission" indicator per category, so this is a sum
# of the closest available count per phase: ANC enrollment, delivery volume
# (labour), and the earliest/most common postnatal contact (PNC -- there's
# no distinct PNC *visit-count* indicator in the current 52, so the 7-day
# postnatal check is used as the closest proxy). Neonatal uses live births
# as the newborn population base.
_AGG_ADMISSION_IDS = {
    "anc": "mnid_anc_moh_002",         # new_anc_registrations
    "labour": "mnid_lab_core_totalbirths",
    "pnc": "mnid_pnc_core_mocheck7d",  # mothers_checked_within_7_days
}

# 4 of the 5 maternal complications have a real DHIS2 mapping (a true
# percentage already computed against PCT_DENOMINATOR, see
# mnid/dhis2/mnid_publish.py); none of the 3 neonatal complications do.
_AGG_MATERNAL_COMPLICATION_IDS = {
    "Pre-eclampsia and Eclampsia": "mnid_lab_core_eclampsia",
    "Postpartum Haemorrhage": "mnid_lab_core_pph",
    "Maternal Sepsis": "mnid_lab_core_004",
    "Obstructed or Prolonged Labour": "mnid_lab_core_obstructedlabour",
}


def _agg_metric_snapshot(
    agg_df: pd.DataFrame,
    start_date,
    end_date,
    facility_codes: list[str] | None = None,
    districts: list[str] | None = None,
) -> dict:
    """DHIS2-aggregate equivalent of _metric_snapshot -- same return shape.

    The 7 birth/death counts DHIS2 maps onto directly, plus
    maternal_admissions/neonatal_admissions derived from _AGG_ADMISSION_IDS
    (see its docstring). completeness has no DHIS2 counterpart and stays
    None so the summary card can render "N/A" instead of a misleading 0.
    """
    counts = {}
    for key, mnid_id in _AGG_METRIC_IDS.items():
        num, _den, _pct = _agg_coverage(
            agg_df, mnid_id, start_date, end_date,
            facility_codes=facility_codes, districts=districts, grain='monthly',
        )
        counts[key] = num

    anc_count, _den, _pct = _agg_coverage(
        agg_df, _AGG_ADMISSION_IDS["anc"], start_date, end_date,
        facility_codes=facility_codes, districts=districts, grain='monthly',
    )
    pnc_count, _den, _pct = _agg_coverage(
        agg_df, _AGG_ADMISSION_IDS["pnc"], start_date, end_date,
        facility_codes=facility_codes, districts=districts, grain='monthly',
    )
    maternal_admissions = anc_count + counts["total_births"] + pnc_count
    neonatal_admissions = counts["live_births"]

    return {
        "maternal_admissions": maternal_admissions,
        "neonatal_admissions": neonatal_admissions,
        "live_births": counts["live_births"],
        "total_births": counts["total_births"],
        "fresh_stillbirths": counts["fresh_stillbirths"],
        "macerated_stillbirths": counts["macerated_stillbirths"],
        "maternal_deaths": counts["maternal_deaths"],
        "neonatal_deaths": counts["neonatal_deaths"],
        "stillbirths": counts["stillbirths"],
        "institutional_mmr": _safe_div(counts["maternal_deaths"], counts["live_births"], 100000),
        "neonatal_mortality_rate": _safe_div(counts["neonatal_deaths"], counts["live_births"], 1000),
        "stillbirth_rate": _safe_div(counts["stillbirths"], counts["total_births"], 1000),
        "fresh_stillbirth_pct": _safe_div(counts["fresh_stillbirths"], counts["stillbirths"], 100),
        "macerated_stillbirth_pct": _safe_div(counts["macerated_stillbirths"], counts["stillbirths"], 100),
        "completeness": None,
    }


def _monthly_series(df: pd.DataFrame, mask: pd.Series, unique_col: str = "person_id") -> pd.DataFrame:
    if df is None or df.empty or "Date" not in df.columns or unique_col not in df.columns:
        return pd.DataFrame(columns=["month", "value"])
    working = df.loc[mask, ["Date", unique_col]].dropna().copy()
    if working.empty:
        return pd.DataFrame(columns=["month", "value"])
    working["month"] = pd.to_datetime(working["Date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    summary = (
        working.dropna(subset=["month"])
        .groupby("month")[unique_col]
        .nunique()
        .reset_index(name="value")
        .sort_values("month")
    )
    summary = summary.tail(12)
    if summary.empty:
        return summary
    full_months = pd.date_range(summary["month"].min(), summary["month"].max(), freq="MS")
    return (
        summary.set_index("month")
        .reindex(full_months, fill_value=0)
        .rename_axis("month")
        .reset_index()
    )


def _monthly_multiseries(series_map: dict[str, tuple[pd.Series, str]], df: pd.DataFrame, unique_col: str = "person_id") -> pd.DataFrame:
    frames = []
    for label, (mask, color) in series_map.items():
        series_df = _monthly_series(df, mask, unique_col)
        if series_df.empty:
            continue
        frames.append(series_df.assign(series=label, color=color))
    if not frames:
        return pd.DataFrame(columns=["month", "value", "series", "color"])
    return pd.concat(frames, ignore_index=True)


def _agg_monthly_series(
    agg_df: pd.DataFrame,
    mnid_id: str,
    start_date,
    end_date,
    facility_codes: list[str] | None = None,
    districts: list[str] | None = None,
    value_field: str = "numerator",
) -> pd.DataFrame:
    """DHIS2-aggregate equivalent of _monthly_series -- same ['month', 'value'] shape.

    value_field='numerator' for count trend charts (Total Births, mortality,
    stillbirths); 'pct' for indicators that are already a rate against their
    PCT_DENOMINATOR pair (the mapped complication charts) -- see
    mnid/dhis2/mnid_publish.py::PCT_DENOMINATOR.
    """
    series = _agg_time_series(
        agg_df, mnid_id, grain='monthly',
        facility_codes=facility_codes, districts=districts,
        start_date=start_date, end_date=end_date,
    )
    if series.empty:
        return pd.DataFrame(columns=["month", "value"])
    out = series.rename(columns={"period_start": "month", value_field: "value"})
    return out[["month", "value"]]


def _agg_monthly_multiseries(
    series_map: dict[str, tuple[str, str]],
    agg_df: pd.DataFrame,
    start_date,
    end_date,
    facility_codes: list[str] | None = None,
    districts: list[str] | None = None,
) -> pd.DataFrame:
    """DHIS2-aggregate equivalent of _monthly_multiseries. series_map: {label: (mnid_id, color)}."""
    frames = []
    for label, (mnid_id, color) in series_map.items():
        series_df = _agg_monthly_series(agg_df, mnid_id, start_date, end_date, facility_codes, districts)
        if series_df.empty:
            continue
        frames.append(series_df.assign(series=label, color=color))
    if not frames:
        return pd.DataFrame(columns=["month", "value", "series", "color"])
    return pd.concat(frames, ignore_index=True)


def _monthly_rate_series(
    df: pd.DataFrame,
    numerator_mask: pd.Series,
    denominator_mask: pd.Series,
    unique_col: str = "person_id",
    scale: float = 100.0,
) -> pd.DataFrame:
    if df is None or df.empty or "Date" not in df.columns or unique_col not in df.columns:
        return pd.DataFrame(columns=["month", "value"])
    numerator = _monthly_series(df, numerator_mask, unique_col)
    denominator = _monthly_series(df, denominator_mask, unique_col)
    if denominator.empty:
        return pd.DataFrame(columns=["month", "value"])
    merged = denominator.rename(columns={"value": "denominator"}).merge(
        numerator.rename(columns={"value": "numerator"}),
        on="month",
        how="left",
    )
    merged["numerator"] = pd.to_numeric(merged["numerator"], errors="coerce").fillna(0)
    merged["denominator"] = pd.to_numeric(merged["denominator"], errors="coerce").fillna(0)
    merged["value"] = merged.apply(
        lambda row: round((row["numerator"] / row["denominator"]) * scale, 1) if row["denominator"] > 0 else 0.0,
        axis=1,
    )
    return merged[["month", "value"]]


def _delta_percent(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return round(((current - previous) / previous) * 100, 1)


def _sparkline_figure(series: pd.DataFrame, color: str) -> go.Figure:
    fig = go.Figure()
    if not series.empty:
        smooth_values, _ = _moving_average_values(series["value"].tolist(), "monthly")
        valid_values = [value for value in series["value"].tolist() if value is not None]
        y_min = min(valid_values) if valid_values else 0
        y_max = max(valid_values) if valid_values else 1
        y_span = max(y_max - y_min, 1)
        y_floor = max(y_min - (y_span * 0.18), 0)
        y_ceiling = y_max + (y_span * 0.12)
        r = int(color[1:3], 16) if color.startswith("#") and len(color) == 7 else 21
        g_v = int(color[3:5], 16) if color.startswith("#") and len(color) == 7 else 128
        b = int(color[5:7], 16) if color.startswith("#") and len(color) == 7 else 61

        fig.add_trace(go.Scatter(
            x=series["month"],
            y=smooth_values,
            mode="lines+markers",
            line=dict(color=color, width=3, shape="spline", smoothing=1.0),
            marker=dict(size=5, color=color, line=dict(color="#ffffff", width=1)),
            fill="tozeroy",
            fillcolor=f"rgba({r},{g_v},{b},0.10)",
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=series["month"],
            y=series["value"],
            mode="lines",
            line=dict(color=color, width=1.4, dash="dot"),
            opacity=0.42,
            hoverinfo="skip",
        ))
        fig.update_yaxes(range=[y_floor, y_ceiling])
    fig.update_layout(
        margin=dict(l=0, r=0, t=4, b=0),
        height=64,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig


def _trend_subtitle(title: str) -> str:
    custom = {
        "Total Births": "Reported total births across the selected reporting period.",
        "Maternal Mortality": "Reported maternal deaths in the selected scope.",
        "Neonatal Mortality": "Reported neonatal deaths in the selected scope.",
        "Stillbirths": "Stillbirth trend, including fresh and macerated cases.",
        "Pre-eclampsia and Eclampsia": "Monthly hypertensive complication rate as a percent of total births.",
        "Postpartum Haemorrhage": "Monthly postpartum haemorrhage rate as a percent of total births.",
        "Maternal Sepsis": "Monthly maternal sepsis rate as a percent of total births.",
        "Obstructed or Prolonged Labour": "Monthly obstructed or prolonged labour rate as a percent of total births.",
        "Ruptured Uterus": "Monthly ruptured uterus rate as a percent of total births.",
        "Birth Asphyxia": "Monthly birth asphyxia rate as a percent of live births.",
        "Preterm Birth": "Monthly preterm birth rate as a percent of live births.",
        "Neonatal Sepsis": "Monthly neonatal sepsis rate as a percent of live births.",
    }
    return custom.get(title, "Reported cases in the selected scope.")


def _summary_card(title: str, value: str, subtitle: str, accent: str) -> dmc.Paper:
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="md",
        style={
            "background": "#fff",
            "borderColor": "#e2e8f0",
            "borderTop": f"3px solid {accent}",
            "height": "100%",
        },
        children=[
            html.Div(title, style={
                "fontSize": "10px",
                "fontWeight": "700",
                "color": "#64748b",
                "textTransform": "uppercase",
                "letterSpacing": ".06em",
                "marginBottom": "10px",
            }),
            html.Div(value, style={
                "fontSize": "24px", "fontWeight": "800", "color": "#0f172a",
                "letterSpacing": "-.03em", "lineHeight": "1",
            }),
            html.Div(subtitle, style={"fontSize": "11px", "color": "#94a3b8", "marginTop": "5px"}),
        ],
    )


_MORTALITY_TOKENS = {
    "Maternal Deaths":  {"accent": "#e11d48", "bg": "#fff1f2", "bdr": "#fecdd3", "shadow_rgba": "225,29,72"},
    "Neonatal Deaths":  {"accent": "#d97706", "bg": "#fffbeb", "bdr": "#fde68a", "shadow_rgba": "217,119,6"},
    "Stillbirths":      {"accent": "#7c3aed", "bg": "#f5f3ff", "bdr": "#ddd6fe", "shadow_rgba": "124,58,237"},
}


def _mortality_card(
    title: str,
    count: int,
    rate_label: str,
    rate_value: float,
    delta_count: int,
    color: str,
    background: str,
    breakdown: list[tuple[str, str]] | None = None,
):
    tokens = _MORTALITY_TOKENS.get(title, {"accent": color, "bg": background, "bdr": color, "shadow_rgba": "0,0,0"})
    accent = tokens["accent"]
    delta_prefix = "+" if delta_count > 0 else ""
    delta_label = f"{delta_prefix}{delta_count:,}"
    is_worse = delta_count > 0
    breakdown = breakdown or []
    breakdown_widths = []
    if breakdown:
        parsed_values = []
        for _label, value in breakdown:
            pct_match = None
            if isinstance(value, str):
                import re
                pct_match = re.search(r"(\d+(?:\.\d+)?)%", value)
            parsed_values.append(float(pct_match.group(1)) if pct_match else 0.0)
        total_pct = sum(parsed_values)
        if total_pct > 0:
            breakdown_widths = [max((pct / total_pct) * 100, 0) for pct in parsed_values]
        else:
            breakdown_widths = [50.0 for _ in breakdown]
    return dmc.Paper(
        withBorder=False,
        radius="lg",
        p="lg",
        style={
            "background": tokens["bg"],
            "border": f"1px solid {tokens['bdr']}",
            "borderTop": f"3px solid {accent}",
            "borderRadius": "14px",
            "position": "relative",
            "overflow": "hidden",
        },
        children=[
            html.Div(f"⬤ {title}", style={
                "fontSize": "10px", "fontWeight": "700", "letterSpacing": ".08em",
                "textTransform": "uppercase", "color": accent, "marginBottom": "10px",
            }),
            html.Div([
                html.Div([
                    html.Div(f"{count:,}", style={
                        "fontSize": "44px", "fontWeight": "800", "letterSpacing": "-.05em",
                        "color": accent, "lineHeight": "0.95", "marginBottom": "8px",
                    }),
                    html.Div("Recorded in the selected reporting period", style={
                        "fontSize": "11px", "color": "#64748b",
                    }),
                ], style={"flex": "1", "minWidth": "0"}),
                html.Div([
                    html.Div("Change vs last period", style={
                        "fontSize": "10px", "fontWeight": "700", "color": "#64748b",
                        "textTransform": "uppercase", "letterSpacing": ".05em", "marginBottom": "6px",
                    }),
                    html.Span(
                        f"{'Increase' if is_worse else 'Decrease'} {delta_label}",
                        style={
                            "fontSize": "12px", "fontWeight": "800", "padding": "5px 10px",
                            "borderRadius": "999px",
                            "background": "#FEE2E2" if is_worse else "#DCFCE7",
                            "color": "#DC2626" if is_worse else "#15803D",
                            "display": "inline-block",
                        },
                    ),
                ], style={"minWidth": "170px"}),
            ], style={"display": "flex", "gap": "14px", "justifyContent": "space-between", "alignItems": "flex-start", "marginBottom": "12px", "flexWrap": "wrap"}),
            html.Hr(style={"border": "none", "borderTop": "1px solid rgba(0,0,0,.07)", "margin": "10px 0"}),
            html.Div([
                html.Div([
                    html.Div(rate_label, style={"fontSize": "10px", "color": "#64748b", "marginBottom": "4px"}),
                    html.Div(f"{rate_value:,.1f}", style={"fontSize": "18px", "fontWeight": "800", "color": "#0f172a"}),
                ]),
                html.Div([
                    html.Div("Interpretation", style={"fontSize": "10px", "color": "#64748b", "marginBottom": "4px"}),
                    html.Div(
                        "Stillbirth burden needs attention" if count > 0 else "No stillbirths recorded",
                        style={"fontSize": "12px", "fontWeight": "700", "color": "#dc2626" if count > 0 else "#16a34a"},
                    ),
                ]),
            ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"}),
            *([
                html.Div([
                    html.Div("Stillbirth breakdown", style={
                        "fontSize": "10px", "fontWeight": "700", "color": "#64748b",
                        "textTransform": "uppercase", "letterSpacing": ".05em", "marginBottom": "8px",
                    }),
                    html.Div([
                        html.Div(style={
                            "height": "10px",
                            "width": f"{breakdown_widths[idx]:.1f}%",
                            "background": ["#8B5CF6", "#C084FC"][idx % 2],
                        })
                        for idx, _ in enumerate(breakdown)
                    ], style={
                        "display": "flex",
                        "width": "100%",
                        "overflow": "hidden",
                        "borderRadius": "999px",
                        "background": "#E9D5FF",
                        "marginBottom": "10px",
                    }),
                    html.Div([
                        html.Div([
                            html.Div(label, style={"fontSize": "11px", "fontWeight": "700", "color": accent, "marginBottom": "4px"}),
                            html.Div(value, style={"fontSize": "12px", "fontWeight": "600", "color": "#334155"}),
                        ], style={
                            "padding": "10px 12px",
                            "background": "#fff",
                            "border": f"1px solid rgba({tokens['shadow_rgba']},.16)",
                            "borderRadius": "10px",
                        })
                        for label, value in breakdown
                    ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"})
                ], style={"marginTop": "14px"})
            ] if breakdown else []),
        ],
    )


def _ranking_list(title: str, rows: list[tuple[str, int]], color_scale: list[str]):
    items = []
    for index, (label, value) in enumerate(rows[:4], start=1):
        items.append(
            dmc.Group(
                justify="space-between",
                mt="sm",
                children=[
                    dmc.Group(gap="sm", children=[
                        html.Div(style={"width": "9px", "height": "9px", "borderRadius": "999px", "background": color_scale[min(index - 1, len(color_scale) - 1)]}),
                        dmc.Text(f"{index}. {label}", size="sm", c=TEXT),
                    ]),
                    dmc.Text(f"{value:,}", size="sm", fw=700, c=color_scale[min(index - 1, len(color_scale) - 1)]),
                ],
            )
        )
    return dmc.Paper(withBorder=True, radius="md", p="md", style={"height": "100%"}, children=[dmc.Text(title, fw=700, size="sm"), *items])


def _stacked_mortality_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return fig
    fig.add_trace(go.Bar(x=df["District"], y=df["maternal"],  name="Maternal",  marker_color=MORTALITY_ROSE, marker_line_width=0))
    fig.add_trace(go.Bar(x=df["District"], y=df["neonatal"],  name="Neonatal",  marker_color=NEONATAL_ORANGE, marker_line_width=0))
    fig.add_trace(go.Bar(x=df["District"], y=df["stillbirth"], name="Stillbirth", marker_color=STILLBIRTH_BLUE, marker_line_width=0))
    fig.update_layout(**_EXEC_CHART_LAYOUT)
    fig.update_layout(
        barmode="stack",
        height=CHART_HEIGHT_LG,
        margin=dict(l=32, r=14, t=14, b=72),
        xaxis=dict(
            showgrid=False, showline=False, zeroline=False,
            tickfont=dict(size=10, color="#94a3b8"),
            tickangle=-18,
            automargin=True,
        ),
    )
    return fig


def _mortality_distribution_chart(df: pd.DataFrame, title: str, color: str) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return fig
    r = int(color[1:3], 16) if color.startswith("#") and len(color) == 7 else 0
    g_v = int(color[3:5], 16) if color.startswith("#") and len(color) == 7 else 0
    b = int(color[5:7], 16) if color.startswith("#") and len(color) == 7 else 0
    fig.add_trace(go.Bar(
        x=df["District"], y=df["value"],
        marker=dict(color=f"rgba({r},{g_v},{b},0.75)", line=dict(color=color, width=0.5)),
    ))
    fig.update_layout(**_EXEC_CHART_LAYOUT)
    fig.update_layout(
        height=CHART_HEIGHT_MD,
        margin=dict(l=32, r=14, t=14, b=64),
        xaxis=dict(
            showgrid=False, showline=False, zeroline=False,
            tickfont=dict(size=10, color="#94a3b8"),
            tickangle=-18,
            automargin=True,
        ),
    )
    return fig


def render_country_profile(
    df: pd.DataFrame, scope_meta: dict | None = None, indicator_label: str = "Maternal Indicators",
    start_date=None, end_date=None,
) -> html.Div:
    profile_name = _profile_scope_name(scope_meta)
    df = _copy_df(df)
    prev_df = _prior_period_df(df)

    # DHIS2 mode: source the metrics/trends that have a real DHIS2 mapping
    # (see _AGG_METRIC_IDS / mnid/dhis2/mnid_publish.py::PCT_DENOMINATOR) from
    # the aggregate instead of scanning raw MAHIS rows, so Country Profile
    # actually reflects MNID_DATA_SOURCE='dhis2' like the rest of MNID
    # already does. Falls back to the existing row-level path if the
    # aggregate isn't published yet, so this never breaks the page.
    agg_df = _get_aggregate(route='dhis2') if (scope_meta or {}).get('route') == 'dhis2' else None
    use_dhis2 = agg_df is not None and not agg_df.empty
    if use_dhis2:
        # Narrow to just the ~11 indicators Country Profile needs, once, up
        # front. query_coverage/query_time_series each re-filter by exact
        # indicator_id internally (an object-dtype string comparison, slow
        # over the full ~600K-row DHIS2 aggregate) -- with ~24 calls per
        # render (7 metrics x current+previous period, 4 trend series, 4
        # complications), that's 24 full-table scans instead of 1.
        _cp_agg_ids = (
            set(_AGG_METRIC_IDS.values())
            | set(_AGG_MATERNAL_COMPLICATION_IDS.values())
            | set(_AGG_ADMISSION_IDS.values())
        )
        agg_df = agg_df[agg_df['indicator_id'].isin(_cp_agg_ids)]
    facility_codes = districts = None

    if use_dhis2:
        _, facility_codes, districts = _resolve_scope_filters(df, scope_meta or {})
        start = pd.to_datetime(start_date) if start_date else None
        end = pd.to_datetime(end_date) if end_date else None
        if start is None or end is None:
            start, end = _period_bounds(df)
        if start is not None and end is not None:
            window_days = max((end - start).days, 1)
            prev_end = start - pd.Timedelta(days=1)
            prev_start = prev_end - pd.Timedelta(days=window_days - 1)
            current_metrics = _agg_metric_snapshot(agg_df, start, end, facility_codes, districts)
            previous_metrics = _agg_metric_snapshot(agg_df, prev_start, prev_end, facility_codes, districts)
        else:
            current_metrics = _agg_metric_snapshot(agg_df, None, None, facility_codes, districts)
            previous_metrics = dict(current_metrics)
    else:
        current_metrics = _metric_snapshot(df)
        previous_metrics = _metric_snapshot(prev_df)
        start, end = _period_bounds(df)

    period_label = f"{start.strftime('%d %b %Y') if start is not None else 'N/A'} - {end.strftime('%d %b %Y') if end is not None else 'N/A'}"
    updated_label = end.strftime("%d %b %Y, %H:%M") if end is not None else "Unavailable"

    scope_items = _hierarchy_scope(df, scope_meta, period_label)
    facilities_reporting = int(df["Facility_CODE"].dropna().astype(str).nunique()) if "Facility_CODE" in df.columns else 0
    districts_covered = int(df["District"].dropna().astype(str).nunique()) if "District" in df.columns else 0

    _fmt_count = lambda v: f"{v:,}" if v is not None else "N/A"
    summary_cards = [
        _summary_card("Maternity Unit Admissions", _fmt_count(current_metrics['maternal_admissions']), "ANC, labour, and PNC encounters", PRIMARY_GREEN),
        _summary_card("Neonatal Care Unit Admissions", _fmt_count(current_metrics['neonatal_admissions']), "Newborn care encounters", NEONATAL_ORANGE),
        _summary_card("Total Births", f"{current_metrics['total_births']:,}", "Live births and stillbirths", STILLBIRTH_BLUE),
        _summary_card("Live Births", f"{current_metrics['live_births']:,}", "Outcome recorded as live birth", SUCCESS_GREEN),
        _summary_card("Stillbirths", f"{current_metrics['stillbirths']:,}", "Stillbirths in current reporting period", "#7C3AED"),
        _summary_card("Maternal Deaths", f"{current_metrics['maternal_deaths']:,}", "Deaths recorded in selected scope", MORTALITY_ROSE),
        _summary_card("Neonatal Deaths", f"{current_metrics['neonatal_deaths']:,}", "Deaths recorded in selected scope", WARNING_AMBER),
    ]

    mortality_specs = [
        ("Maternal Deaths", current_metrics["maternal_deaths"], "MMR per 100k live births",   current_metrics["institutional_mmr"],      current_metrics["maternal_deaths"]  - previous_metrics["maternal_deaths"],  MORTALITY_ROSE,   "#FFF1F2", None),
        ("Neonatal Deaths", current_metrics["neonatal_deaths"], "NMR per 1,000 live births",  current_metrics["neonatal_mortality_rate"], current_metrics["neonatal_deaths"] - previous_metrics["neonatal_deaths"],   NEONATAL_ORANGE, "#FFF8EB", None),
        (
            "Stillbirths",
            current_metrics["stillbirths"],
            "SBR per 1,000 total births",
            current_metrics["stillbirth_rate"],
            current_metrics["stillbirths"] - previous_metrics["stillbirths"],
            STILLBIRTH_BLUE,
            "#EFF6FF",
            [
                ("Fresh stillbirths", f"{current_metrics['fresh_stillbirth_pct']:.1f}% ({current_metrics['fresh_stillbirths']:,})"),
                ("Macerated stillbirths", f"{current_metrics['macerated_stillbirth_pct']:.1f}% ({current_metrics['macerated_stillbirths']:,})"),
            ] if current_metrics["stillbirths"] > 0 else [
                ("Fresh stillbirths", "Breakdown unavailable"),
                ("Macerated stillbirths", "Breakdown unavailable"),
            ],
        ),
    ]

    if use_dhis2:
        total_births_series = _agg_monthly_series(agg_df, "mnid_lab_core_totalbirths", start, end, facility_codes, districts)
        maternal_death_series = _agg_monthly_series(agg_df, "mnid_pnc_overview_004", start, end, facility_codes, districts)
        neonatal_death_series = _agg_monthly_series(agg_df, "mnid_nb_overview_002", start, end, facility_codes, districts)
        stillbirth_trend_series = _agg_monthly_multiseries({
            "Total stillbirths": ("mnid_lab_overview_005", STILLBIRTH_BLUE),
            "Fresh stillbirths": ("mnid_lab_core_freshstillbirths", "#DB2777"),
            "Macerated stillbirths": ("mnid_lab_core_maceratedstillbirths", "#7C3AED"),
        }, agg_df, start, end, facility_codes, districts)
        # Only used by the row-level maternal/neonatal complication loops below.
        live_birth_denominator_mask = total_birth_denominator_mask = None
    else:
        maternal_death_series = _monthly_series(df, _yn_mask(df, "mnid_pnc_maternal_death"), "person_id")
        neonatal_death_series = _monthly_series(df, _contains_mask(df, "obs_value_coded", ["Died", "Dead", "Death", "Neonatal death"]), "person_id")
        live_birth_denominator_mask = (
            _contains_mask(df, "concept_name", ["Outcome of the delivery"])
            & _contains_mask(df, "obs_value_coded", ["Live birth", "Live births", "Alive"])
        )
        total_birth_denominator_mask = (
            _contains_mask(df, "concept_name", ["Outcome of the delivery", "Status of baby", "Admission outcome"])
            & _contains_mask(
                df,
                "obs_value_coded",
                [
                    "Live birth",
                    "Live births",
                    "Alive",
                    "Stillbirth",
                    "Fresh stillbirth",
                    "Macerated stillbirth",
                    "Fresh still birth",
                    "Macerated still birth",
                ],
            )
        )
        total_births_series = _monthly_multiseries({"Total births": (
            _contains_mask(df, "concept_name", ["Outcome of the delivery", "Status of baby", "Admission outcome"]),
            PRIMARY_GREEN,
        )}, df)
        total_births_series = total_births_series[["month", "value"]].copy() if not total_births_series.empty else pd.DataFrame(columns=["month", "value"])
        stillbirth_trend_series = _monthly_multiseries({
            "Total stillbirths": (_yn_mask(df, "mnid_labour_stillbirth"), STILLBIRTH_BLUE),
            "Fresh stillbirths": (
                _contains_mask(df, "obs_value_coded", ["Fresh stillbirth", "Fresh still birth"]),
                "#DB2777",
            ),
            "Macerated stillbirths": (
                _contains_mask(df, "obs_value_coded", ["Macerated stillbirth", "Macerated still birth"]),
                "#7C3AED",
            ),
        }, df)

    maternal_complication_specs = [
        ("Pre-eclampsia and Eclampsia", MORTALITY_ROSE, _yn_mask(df, "mnid_labour_eclampsia") | _contains_mask(df, "obs_value_coded", ["Pre-eclampsia", "Pre eclampsia", "Preeclampsia", "Eclampsia"])),
        ("Postpartum Haemorrhage", WARNING_AMBER, _yn_mask(df, "mnid_labour_pph")),
        ("Maternal Sepsis", "#B91C1C", _yn_mask(df, "mnid_labour_maternal_sepsis")),
        ("Obstructed or Prolonged Labour", "#7C3AED", _yn_mask(df, "mnid_labour_obstructed_labour") | _contains_mask(df, "obs_value_coded", ["Obstructed labour", "Prolonged labour", "Prolonged Labor"])),
        ("Ruptured Uterus", "#475569", _contains_mask(df, "obs_value_coded", ["Ruptured uterus", "Uterine rupture"])),
    ]
    neonatal_complication_specs = [
        ("Birth Asphyxia", "#D97706", _yn_mask(df, "mnid_newborn_birth_asphyxia")),
        ("Preterm Birth", PRIMARY_GREEN, _yn_mask(df, "mnid_labour_preterm")),
        ("Neonatal Sepsis", ADMISSIONS_BLUE, _yn_mask(df, "mnid_newborn_sepsis")),
    ]
    # 4 of the 5 maternal complications have a real DHIS2 mapping (with a
    # true percentage already computed against PCT_DENOMINATOR, see
    # mnid/dhis2/mnid_publish.py); none of the 3 neonatal complications do.
    # Unmapped ones get an empty series -- same "no data" rendering
    # _trend_chart_payload already falls back to for sparse MAHIS periods.
    maternal_complication_cards = []
    for title, color, mask in maternal_complication_specs:
        chart_key = _chart_key_slug(title)
        if use_dhis2:
            mnid_id = _AGG_MATERNAL_COMPLICATION_IDS.get(title)
            series_df = (
                _agg_monthly_series(agg_df, mnid_id, start, end, facility_codes, districts, value_field="pct")
                if mnid_id else pd.DataFrame(columns=["month", "value"])
            )
        else:
            series_df = _monthly_rate_series(df, mask, total_birth_denominator_mask, "person_id")
        maternal_complication_cards.append(_trend_chart_payload(
            chart_key,
            title,
            _trend_subtitle(title),
            color,
            "Rate (%)",
            series_df,
            multi=False,
        )["card"])
    neonatal_complication_cards = []
    for title, color, mask in neonatal_complication_specs:
        chart_key = _chart_key_slug(title)
        series_df = (
            pd.DataFrame(columns=["month", "value"]) if use_dhis2
            else _monthly_rate_series(df, mask, live_birth_denominator_mask, "person_id")
        )
        neonatal_complication_cards.append(_trend_chart_payload(
            chart_key,
            title,
            _trend_subtitle(title),
            color,
            "Rate (%)",
            series_df,
            multi=False,
        )["card"])

    total_births_chart = _trend_chart_payload(
        "total-births",
        "Total Births",
        "Birth volume over time",
        PRIMARY_GREEN,
        "Births",
        total_births_series,
        multi=False,
    )["card"]
    maternal_mortality_chart = _trend_chart_payload(
        "maternal-mortality",
        "Maternal Mortality",
        _trend_subtitle("Maternal Mortality"),
        MORTALITY_ROSE,
        "Deaths",
        maternal_death_series,
        multi=False,
    )["card"]
    neonatal_mortality_chart = _trend_chart_payload(
        "neonatal-mortality",
        "Neonatal Mortality",
        _trend_subtitle("Neonatal Mortality"),
        NEONATAL_ORANGE,
        "Deaths",
        neonatal_death_series,
        multi=False,
    )["card"]
    stillbirths_chart = _trend_chart_payload(
        "stillbirths",
        "Stillbirths",
        _trend_subtitle("Stillbirths"),
        STILLBIRTH_BLUE,
        "Cases",
        stillbirth_trend_series,
        multi=True,
    )["card"]

    hero = dmc.Paper(
        withBorder=True,
        radius="lg",
        shadow="xs",
        p="xl",
        style={"marginBottom": "20px", "borderColor": "#e2e8f0"},
        children=[
            html.Div(profile_name["eyebrow"], style={
                "fontSize": "10px", "fontWeight": "700", "color": "#0f766e",
                "letterSpacing": ".12em", "textTransform": "uppercase",
                "marginBottom": "10px",
            }),
            html.Div([
                html.Div([
                    html.H1("Maternal and Neonatal Outcomes Dashboard", style={
                        "fontSize": "26px", "fontWeight": "800", "color": "#0f172a",
                        "letterSpacing": "-.04em", "lineHeight": "1.15", "marginBottom": "6px",
                    }),
                    html.P(f"{profile_name['overview']} · {indicator_label} · Evidence for action · Decision support", style={
                        "fontSize": "13px", "color": "#64748b", "marginBottom": "16px",
                    }),
                    html.Div([
                        html.Span("Live", style={
                            "background": "#ecfdf5", "border": "1px solid #bbf7d0",
                            "color": "#15803d", "fontSize": "10px", "fontWeight": "700",
                            "padding": "4px 10px", "borderRadius": "99px",
                        }),
                        html.Span(period_label, style={
                            "background": "#f8fafc", "border": "1px solid #e2e8f0",
                            "color": "#475569", "fontSize": "10px", "fontWeight": "700",
                            "padding": "4px 10px", "borderRadius": "99px",
                        }),
                        html.Span(f"{districts_covered} Districts · {facilities_reporting} Facilities", style={
                            "background": "#f8fafc", "border": "1px solid #e2e8f0",
                            "color": "#475569", "fontSize": "10px", "fontWeight": "700",
                            "padding": "4px 10px", "borderRadius": "99px",
                        }),
                    ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap"}),
                ], style={"flex": "1", "minWidth": "280px"}),
            ], style={"display": "flex", "gap": "18px", "flexWrap": "wrap", "alignItems": "stretch"}),
        ],
    )

    # ---------- Alert banner ----------
    alert = None
    _md = current_metrics["maternal_deaths"]
    _nd = current_metrics["neonatal_deaths"]
    _sb = current_metrics["stillbirths"]
    if _md > 0 or _nd > 0 or _sb > 0:
        alert = _exec_alert_banner(
            maternal_deaths=_md,
            mmr=current_metrics["institutional_mmr"],
            neonatal_deaths=_nd,
            stillbirths=_sb,
        )

    # ---------- Scope info band ----------
    scope_band = html.Div([
        html.Div([
            html.Span(item["label"], style={"fontSize": "9px", "fontWeight": "700", "color": "#94a3b8", "textTransform": "uppercase", "letterSpacing": ".07em", "display": "block", "marginBottom": "2px"}),
            html.Span(item["value"], style={"fontSize": "11px", "fontWeight": "600", "color": "#0f172a"}),
        ], style={"padding": "8px 14px", "borderRight": "1px solid #e2e8f0"})
        for item in scope_items
    ] + [
        html.Div([
            html.Span("Completeness", style={"fontSize": "9px", "fontWeight": "700", "color": "#94a3b8", "textTransform": "uppercase", "letterSpacing": ".07em", "display": "block", "marginBottom": "2px"}),
            html.Span(
                f"{current_metrics['completeness']:.1f}%" if current_metrics['completeness'] is not None else "N/A",
                style={"fontSize": "11px", "fontWeight": "600", "color": "#0f172a"},
            ),
        ], style={"padding": "8px 14px"}),
    ], style={
        "display": "flex", "flexWrap": "wrap",
        "background": "#f8fafc", "border": "1px solid #e2e8f0",
        "borderRadius": "10px", "overflow": "hidden", "marginBottom": "20px",
    })

    return html.Div(
        className="mnid-executive-page",
        children=[
            hero,
            *([alert] if alert else []),
            scope_band,
            _section_header("Country Summary · Current Reporting Period"),
            _responsive_grid(summary_cards, min_width="200px", gap="14px"),
            _section_header("Mortality Snapshot · Immediate Attention Required"),
            _responsive_grid([_mortality_card(*spec) for spec in mortality_specs], min_width="260px", gap="14px"),
            _section_header("Mortality Trends · 12-Month Run Charts"),
            _two_column_chart_grid([
                total_births_chart,
                maternal_mortality_chart,
                neonatal_mortality_chart,
                stillbirths_chart,
            ]),
            _section_header("Maternal Complications"),
            _two_column_chart_grid(maternal_complication_cards),
            _section_header("Neonatal Complications"),
            _two_column_chart_grid(neonatal_complication_cards),
        ],
    )
