"""Executive Country Profile and Operational Readiness views for MNID."""
from __future__ import annotations

import dash_mantine_components as dmc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from mnid.chart_helpers import _moving_average_values
from mnid.constants import BG, BORDER, DIM, FONT, GRID_C, MUTED, OK_C, TEXT, WARN_C

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


def _metric_snapshot(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {
            "total_admissions": 0,
            "maternal_admissions": 0,
            "neonatal_admissions": 0,
            "total_deliveries": 0,
            "facility_deliveries": 0,
            "live_births": 0,
            "total_births": 0,
            "maternal_deaths": 0,
            "neonatal_deaths": 0,
            "stillbirths": 0,
            "institutional_mmr": 0.0,
            "neonatal_mortality_rate": 0.0,
            "stillbirth_rate": 0.0,
            "completeness": 0.0,
        }

    encounter_col = "encounter_id" if "encounter_id" in df.columns else "person_id"

    maternal_mask = _service_mask(df, ["ANC", "Labour", "PNC"])
    newborn_mask = _service_mask(df, ["Newborn"])
    labour_mask = _service_mask(df, ["Labour"])
    facility_delivery_mask = (
        _contains_mask(df, "concept_name", ["Place of delivery"])
        & _contains_mask(df, "obs_value_coded", ["This facility", "this facility"])
    )
    live_birth_mask = (
        _contains_mask(df, "concept_name", ["Outcome of the delivery"])
        & _contains_mask(df, "obs_value_coded", ["Live birth", "Live births", "Alive"])
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

    total_admissions = _unique_count(df, pd.Series(True, index=df.index), encounter_col)
    maternal_admissions = _unique_count(df, maternal_mask, encounter_col)
    neonatal_admissions = _unique_count(df, newborn_mask, encounter_col)
    total_deliveries = _unique_count(df, labour_mask, encounter_col)
    facility_deliveries = _unique_count(df, facility_delivery_mask, "person_id")
    live_births = _unique_count(df, live_birth_mask, "person_id")
    stillbirths = _unique_count(df, stillbirth_mask, "person_id")
    total_births = live_births + stillbirths
    maternal_deaths = _unique_count(df, maternal_death_mask, "person_id")
    neonatal_deaths = _unique_count(df, neonatal_death_mask, "person_id")

    completeness = 0.0
    if "concept_name" in df.columns:
        completeness = round(df["concept_name"].fillna("").astype(str).str.strip().ne("").mean() * 100, 1)

    return {
        "total_admissions": total_admissions,
        "maternal_admissions": maternal_admissions,
        "neonatal_admissions": neonatal_admissions,
        "total_deliveries": total_deliveries,
        "facility_deliveries": facility_deliveries,
        "live_births": live_births,
        "total_births": total_births,
        "maternal_deaths": maternal_deaths,
        "neonatal_deaths": neonatal_deaths,
        "stillbirths": stillbirths,
        "institutional_mmr": _safe_div(maternal_deaths, live_births, 100000),
        "neonatal_mortality_rate": _safe_div(neonatal_deaths, live_births, 1000),
        "stillbirth_rate": _safe_div(stillbirths, total_births, 1000),
        "completeness": completeness,
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
    return summary.tail(12)


def _delta_percent(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return round(((current - previous) / previous) * 100, 1)


def _sparkline_figure(series: pd.DataFrame, color: str) -> go.Figure:
    fig = go.Figure()
    if not series.empty:
        fig.add_trace(
            go.Scatter(
                x=series["month"],
                y=series["value"],
                mode="lines",
                line=dict(color=color, width=2),
                hoverinfo="skip",
            )
        )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=38,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig


def _moving_average_chart(series: pd.DataFrame, title: str, color: str, target: float | None = None) -> go.Figure:
    fig = go.Figure()
    if series.empty:
        fig.update_layout(
            paper_bgcolor=BG,
            plot_bgcolor=BG,
            height=260,
            margin=dict(l=8, r=8, t=28, b=8),
            annotations=[dict(text="No trend data available", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=12, color=MUTED))],
        )
        return fig

    smoothed, _ = _moving_average_values(series["value"].tolist(), "monthly")
    fig.add_trace(go.Scatter(
        x=series["month"],
        y=series["value"],
        name="Actual",
        mode="lines+markers",
        line=dict(color=color, width=2.2, shape="spline"),
        marker=dict(size=6, color=color),
    ))
    fig.add_trace(go.Scatter(
        x=series["month"],
        y=smoothed,
        name="3-mo avg",
        mode="lines",
        line=dict(color=color, width=1.8, dash="dash"),
        opacity=0.45,
    ))
    if target is not None:
        fig.add_trace(go.Scatter(
            x=series["month"],
            y=[target] * len(series),
            name="Target",
            mode="lines",
            line=dict(color=PRIMARY_GREEN, width=1.5, dash="dot"),
        ))
    fig.update_layout(
        title=dict(text=title, x=0.01, xanchor="left", font=dict(size=14, color=TEXT, family=FONT)),
        height=260,
        margin=dict(l=8, r=8, t=42, b=16),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor="#fff", bordercolor=BORDER, font_size=11),
        xaxis=dict(showgrid=False, zeroline=False, showline=False, tickformat="%b", tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False, tickfont=dict(size=10, color=MUTED)),
        legend=dict(orientation="h", x=0, y=1.14, xanchor="left", font=dict(size=10, color=DIM)),
        hovermode="x unified",
    )
    return fig


def _status_badge(delta_value: float, positive_is_good: bool = True):
    good = delta_value >= 0 if positive_is_good else delta_value <= 0
    color = SUCCESS_GREEN if good else MORTALITY_ROSE
    prefix = "+" if delta_value > 0 else ""
    return html.Div(
        f"{prefix}{delta_value:.1f}%",
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "padding": "3px 8px",
            "borderRadius": "999px",
            "fontSize": "11px",
            "fontWeight": "700",
            "color": color,
            "background": SOFT_GREEN if good else "#FFF1F2",
        },
    )


def _kpi_card(title: str, value: int | float, delta_value: float, series: pd.DataFrame, color: str, note: str):
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="md",
        style={"background": BG, "borderColor": BORDER, "height": "100%"},
        children=[
            dmc.Text(title, size="xs", c="dimmed", tt="uppercase", fw=700, style={"letterSpacing": "0.08em"}),
            dmc.Group(
                justify="space-between",
                align="flex-end",
                mt="xs",
                children=[
                    dmc.Text(f"{int(value):,}" if float(value).is_integer() else f"{value:,.1f}", size="xl", fw=700, c=TEXT),
                    _status_badge(delta_value),
                ],
            ),
            dmc.Text(note, size="xs", c=DIM, mt=4),
            dcc.Graph(
                figure=_sparkline_figure(series, color),
                config={"displayModeBar": False, "responsive": True},
                style={"height": "44px", "marginTop": "8px"},
            ),
        ],
    )


def _mortality_card(title: str, count: int, rate_label: str, rate_value: float, delta_count: int, color: str, background: str):
    delta_prefix = "+" if delta_count > 0 else ""
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="lg",
        style={"background": background, "borderColor": color},
        children=[
            dmc.Text(title, size="sm", fw=700, c=color, tt="uppercase", style={"letterSpacing": "0.06em"}),
            dmc.Text(f"{count:,}", size="3rem", fw=700, c=color, lh=1.0, mt="sm"),
            dmc.Text(f"{rate_label}: {rate_value:,.1f}", size="sm", c=TEXT, mt="xs"),
            html.Div(style={"height": "1px", "background": BORDER, "margin": "12px 0"}),
            dmc.Group(justify="space-between", children=[
                dmc.Text(f"vs. last period", size="sm", c=DIM),
                html.Div(
                    f"{delta_prefix}{delta_count:,}",
                    style={
                        "padding": "2px 8px",
                        "borderRadius": "999px",
                        "fontSize": "11px",
                        "fontWeight": "700",
                        "background": "rgba(255,255,255,0.6)",
                        "color": color,
                    },
                ),
            ]),
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
    fig.add_trace(go.Bar(x=df["District"], y=df["maternal"], name="Maternal", marker_color=MORTALITY_ROSE))
    fig.add_trace(go.Bar(x=df["District"], y=df["neonatal"], name="Neonatal", marker_color=NEONATAL_ORANGE))
    fig.add_trace(go.Bar(x=df["District"], y=df["stillbirth"], name="Stillbirth", marker_color=STILLBIRTH_BLUE))
    fig.update_layout(
        barmode="stack",
        height=290,
        margin=dict(l=8, r=8, t=18, b=18),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        xaxis=dict(showgrid=False, zeroline=False, showline=False, tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False, tickfont=dict(size=10, color=MUTED)),
        legend=dict(orientation="h", x=0, y=1.12, xanchor="left", font=dict(size=10, color=DIM)),
    )
    return fig


def _mortality_distribution_chart(df: pd.DataFrame, title: str, color: str) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return fig
    fig.add_trace(go.Bar(x=df["District"], y=df["value"], marker=dict(color=color, line=dict(color=color, width=1)), opacity=0.65))
    fig.update_layout(
        title=dict(text=title, x=0.01, xanchor="left", font=dict(size=14, color=TEXT, family=FONT)),
        height=250,
        margin=dict(l=8, r=8, t=34, b=16),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        xaxis=dict(showgrid=False, zeroline=False, showline=False, tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False, tickfont=dict(size=10, color=MUTED)),
    )
    return fig


def render_country_profile(df: pd.DataFrame, scope_meta: dict | None = None, indicator_label: str = "Maternal Indicators") -> html.Div:
    df = _copy_df(df)
    prev_df = _prior_period_df(df)
    current_metrics = _metric_snapshot(df)
    previous_metrics = _metric_snapshot(prev_df)
    start, end = _period_bounds(df)
    period_label = f"{start.strftime('%d %b %Y') if start is not None else 'N/A'} - {end.strftime('%d %b %Y') if end is not None else 'N/A'}"
    updated_label = end.strftime("%d %b %Y, %H:%M") if end is not None else "Unavailable"

    scope_items = _hierarchy_scope(df, scope_meta, period_label)
    facilities_reporting = int(df["Facility_CODE"].dropna().astype(str).nunique()) if "Facility_CODE" in df.columns else 0

    kpi_specs = [
        ("Total Admissions", "total_admissions", ADMISSIONS_BLUE, "12-month reporting window", pd.Series(True, index=df.index)),
        ("Maternal Admissions", "maternal_admissions", PRIMARY_GREEN, "ANC, labour, and PNC service area", _service_mask(df, ["ANC", "Labour", "PNC"])),
        ("Neonatal Admissions", "neonatal_admissions", NEONATAL_ORANGE, "Neonatal care service area", _service_mask(df, ["Newborn"])),
        ("Total Deliveries", "total_deliveries", "#7C3AED", "Labour encounters", _service_mask(df, ["Labour"])),
        ("Live Births", "live_births", PRIMARY_GREEN, "Outcome of delivery = live birth", _contains_mask(df, "obs_value_coded", ["Live birth", "Live births", "Alive"])),
        ("Total Births", "total_births", STILLBIRTH_BLUE, "Live births + stillbirths", _contains_mask(df, "concept_name", ["Outcome of the delivery", "Status of baby", "Admission outcome"])),
    ]

    kpi_cards = []
    for label, key, color, note, mask in kpi_specs:
        series = _monthly_series(df, mask if len(df) else pd.Series(dtype=bool), "encounter_id" if key.endswith("admissions") or key == "total_deliveries" else "person_id")
        delta = _delta_percent(current_metrics[key], previous_metrics[key])
        kpi_cards.append(_kpi_card(label, current_metrics[key], delta, series, color, note))

    mortality_specs = [
        ("Maternal Deaths", current_metrics["maternal_deaths"], "MMR per 100k live births", current_metrics["institutional_mmr"], current_metrics["maternal_deaths"] - previous_metrics["maternal_deaths"], MORTALITY_ROSE, "#FFF1F2"),
        ("Neonatal Deaths", current_metrics["neonatal_deaths"], "NMR per 1,000 live births", current_metrics["neonatal_mortality_rate"], current_metrics["neonatal_deaths"] - previous_metrics["neonatal_deaths"], NEONATAL_ORANGE, "#FFF8EB"),
        ("Stillbirths", current_metrics["stillbirths"], "SBR per 1,000 total births", current_metrics["stillbirth_rate"], current_metrics["stillbirths"] - previous_metrics["stillbirths"], STILLBIRTH_BLUE, "#EFF6FF"),
    ]

    admissions_series = _monthly_series(df, pd.Series(True, index=df.index), "encounter_id")
    maternal_death_series = _monthly_series(df, _yn_mask(df, "mnid_pnc_maternal_death"), "person_id")
    neonatal_death_series = _monthly_series(df, _contains_mask(df, "obs_value_coded", ["Died", "Dead", "Death", "Neonatal death"]), "person_id")
    stillbirth_series = _monthly_series(df, _yn_mask(df, "mnid_labour_stillbirth"), "person_id")

    geography_df = pd.DataFrame()
    if not df.empty and "District" in df.columns:
        geo_work = df.copy()
        geo_work["region"] = geo_work["District"].map(lambda x: DISTRICT_REGION_ZONE.get(str(x), ("Unknown", "Unknown"))[0])
        geo_group = geo_work.groupby("District", as_index=False).agg(
            maternal=("mnid_pnc_maternal_death", lambda s: s.fillna("").astype(str).str.lower().isin({"yes", "true", "1"}).sum() if len(s) else 0),
            neonatal=("obs_value_coded", lambda s: s.fillna("").astype(str).str.lower().isin({"died", "dead", "death", "neonatal death"}).sum() if len(s) else 0),
            stillbirth=("mnid_labour_stillbirth", lambda s: s.fillna("").astype(str).str.lower().isin({"yes", "true", "1"}).sum() if len(s) else 0),
        )
        geo_group["total"] = geo_group[["maternal", "neonatal", "stillbirth"]].sum(axis=1)
        geography_df = geo_group.sort_values("total", ascending=False).head(6)
        region_ranking = (
            geo_work.assign(maternal=_yn_mask(geo_work, "mnid_pnc_maternal_death").astype(int))
            .groupby("region", as_index=False)["maternal"]
            .sum()
            .sort_values("maternal", ascending=False)
        )
        region_rows = [(row["region"], int(row["maternal"])) for _, row in region_ranking.iterrows()]
    else:
        region_rows = []

    hotspot_rows = [(row["District"], int(row["total"])) for _, row in geography_df.iterrows()] if not geography_df.empty else []

    explorer_specs = [
        ("Maternal deaths", MORTALITY_ROSE, geography_df.assign(value=geography_df["maternal"]) if not geography_df.empty else pd.DataFrame(), maternal_death_series),
        ("Neonatal deaths", NEONATAL_ORANGE, geography_df.assign(value=geography_df["neonatal"]) if not geography_df.empty else pd.DataFrame(), neonatal_death_series),
        ("Stillbirths", STILLBIRTH_BLUE, geography_df.assign(value=geography_df["stillbirth"]) if not geography_df.empty else pd.DataFrame(), stillbirth_series),
    ]

    explorer_tabs = dcc.Tabs(
        value="Maternal deaths",
        className="mnid-exec-subtabs",
        children=[
            dcc.Tab(
                label=label,
                value=label,
                className="mnid-exec-subtab",
                selected_className="mnid-exec-subtab--selected",
                children=html.Div(
                    style={"paddingTop": "18px"},
                    children=[
                        dmc.SimpleGrid(
                            cols=2,
                            spacing="lg",
                            children=[
                                dcc.Graph(figure=_mortality_distribution_chart(dist_df[["District", "value"]] if not dist_df.empty else pd.DataFrame(), f"{label} distribution", color), config={"displayModeBar": False}),
                                dcc.Graph(figure=_moving_average_chart(series_df, f"{label[:-1]} trend", color, None), config={"displayModeBar": False}),
                            ],
                        )
                    ],
                ),
            )
            for label, color, dist_df, series_df in explorer_specs
        ],
    )

    return html.Div(
        className="mnid-executive-page",
        children=[
            dmc.Paper(
                withBorder=True,
                radius="xl",
                p="xl",
                style={"background": BG, "borderColor": BORDER, "marginBottom": "18px"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        align="flex-start",
                        children=[
                            dmc.Stack(
                                gap=4,
                                children=[
                                    dmc.Text("Maternal & Newborn Health Dashboard", size="sm", fw=700, c=PRIMARY_GREEN, tt="uppercase", style={"letterSpacing": "0.08em"}),
                                    dmc.Title("Malawi National Overview", order=1, c=TEXT),
                                    dmc.Text(f"{indicator_label} scope · executive summary and national mortality profile", size="sm", c=DIM),
                                ],
                            ),
                            dmc.Stack(
                                gap=6,
                                align="flex-end",
                                children=[
                                    dmc.Badge("Country Profile", size="lg", radius="sm", color="green", variant="light"),
                                    dmc.Text(f"Last updated · {updated_label}", size="sm", c=DIM),
                                    dmc.Text(f"Data completeness · {current_metrics['completeness']:.1f}%", size="sm", c=DIM),
                                    dmc.Text(f"Facilities reporting · {facilities_reporting}", size="sm", c=DIM),
                                ],
                            ),
                        ],
                    )
                ],
            ),
            dmc.Paper(
                withBorder=True,
                radius="md",
                p="md",
                mb="lg",
                style={"background": SOFT_BACKGROUND, "borderColor": BORDER},
                children=[
                    dmc.Text("Scoped by dashboard filters", size="sm", fw=700, mb="sm"),
                    dmc.SimpleGrid(
                        cols=5,
                        spacing="md",
                        children=[
                            dmc.Select(label=item["label"], value=item["value"], data=[item["value"]], disabled=True)
                            for item in scope_items
                        ],
                    ),
                ],
            ),
            dmc.Text("Data Volume · 12-Month Period", size="sm", fw=700, tt="uppercase", style={"letterSpacing": "0.08em", "marginBottom": "10px"}),
            dmc.SimpleGrid(cols=3, spacing="lg", mb="lg", children=kpi_cards),
            dmc.Text("Mortality Snapshot · Immediate Attention Required", size="sm", fw=700, tt="uppercase", style={"letterSpacing": "0.08em", "marginBottom": "10px"}),
            dmc.SimpleGrid(
                cols=3,
                spacing="md",
                mb="lg",
                children=[_mortality_card(*spec) for spec in mortality_specs],
            ),
            dmc.Text("National Trends · 12-Month Run Charts", size="sm", fw=700, tt="uppercase", style={"letterSpacing": "0.08em", "marginBottom": "10px"}),
            dmc.SimpleGrid(
                cols=2,
                spacing="lg",
                mb="lg",
                children=[
                    dcc.Graph(figure=_moving_average_chart(admissions_series, "Admissions trend", ADMISSIONS_BLUE, None), config={"displayModeBar": False}),
                    dcc.Graph(figure=_moving_average_chart(maternal_death_series, "Maternal death trend", MORTALITY_ROSE, current_metrics["institutional_mmr"] / 20 if current_metrics["institutional_mmr"] else None), config={"displayModeBar": False}),
                    dcc.Graph(figure=_moving_average_chart(neonatal_death_series, "Neonatal death trend", NEONATAL_ORANGE, current_metrics["neonatal_mortality_rate"] * 4 if current_metrics["neonatal_mortality_rate"] else None), config={"displayModeBar": False}),
                    dcc.Graph(figure=_moving_average_chart(stillbirth_series, "Stillbirth trend", STILLBIRTH_BLUE, current_metrics["stillbirth_rate"] * 4 if current_metrics["stillbirth_rate"] else None), config={"displayModeBar": False}),
                ],
            ),
            dmc.Text("Where is Mortality Happening? · Geographic Breakdown", size="sm", fw=700, tt="uppercase", style={"letterSpacing": "0.08em", "marginBottom": "10px"}),
            dmc.SimpleGrid(
                cols=2,
                spacing="lg",
                mb="lg",
                children=[
                    _ranking_list("Region ranking · maternal deaths", region_rows or [("No data", 0)], [MORTALITY_ROSE, "#FB7185", "#FCA5A5", "#FECACA"]),
                    dmc.Paper(withBorder=True, radius="md", p="md", children=[dmc.Text("District ranking · all mortality", fw=700, size="sm"), dcc.Graph(figure=_stacked_mortality_chart(geography_df), config={"displayModeBar": False})]),
                ],
            ),
            dmc.SimpleGrid(
                cols=2,
                spacing="lg",
                mb="lg",
                children=[
                    _ranking_list("Facility hotspots", hotspot_rows or [("No data", 0)], [MORTALITY_ROSE, "#FB7185", "#FDA4AF", "#FCD34D"]),
                    dmc.Paper(withBorder=True, radius="md", p="md", children=[dmc.Text("Zone comparison", fw=700, size="sm"), dmc.Text("Derived from district mortality distribution in the current scope.", size="sm", c=DIM, mt="xs")]),
                ],
            ),
            dmc.Text("Mortality Explorer · Interactive", size="sm", fw=700, tt="uppercase", style={"letterSpacing": "0.08em", "marginBottom": "10px"}),
            dmc.Paper(withBorder=True, radius="md", p="md", children=[explorer_tabs]),
        ],
    )
