"""Executive Country Profile and Operational Readiness views for MNID."""
from __future__ import annotations

import dash_mantine_components as dmc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from mnid.chart_helpers import _cov, _moving_average_values
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

_GEIST = "Geist, system-ui, sans-serif"

_EXEC_CHART_LAYOUT = dict(
    paper_bgcolor="white",
    plot_bgcolor="white",
    font=dict(family=_GEIST, color="#64748b", size=11),
    margin=dict(l=44, r=14, t=14, b=28),
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor="#0f172a",
        font_color="white",
        font_size=11,
        font_family=_GEIST,
        bordercolor="#0f172a",
    ),
    xaxis=dict(
        showgrid=False, showline=False, zeroline=False,
        tickfont=dict(size=10, color="#94a3b8"),
        tickcolor="rgba(0,0,0,0)",
    ),
    yaxis=dict(
        showgrid=True, gridcolor="#f1f5f9", gridwidth=1,
        showline=False, zeroline=False,
        tickfont=dict(size=10, color="#94a3b8"),
    ),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
        font=dict(size=11), bgcolor="rgba(0,0,0,0)",
    ),
)


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


def _exec_alert_banner(message: str) -> html.Div:
    return html.Div([
        html.Span("⚠️", style={"fontSize": "14px", "flexShrink": "0", "marginTop": "1px"}),
        html.Div([html.Strong("Mortality Alert — "), message],
                 style={"fontSize": "12px", "lineHeight": "1.55"}),
    ], style={
        "display": "flex", "alignItems": "flex-start", "gap": "12px",
        "background": "#fffbeb", "border": "1px solid #fde68a",
        "borderRadius": "10px", "padding": "12px 16px",
        "marginBottom": "20px", "color": "#78350f",
    })


def _readiness_ring_card(icon: str, name: str, score: float, col: str) -> dmc.Paper:
    p = max(0.0, min(float(score), 100.0))
    if p >= 75:
        bg, tc, lbl = "#dcfce7", "#15803d", "Ready"
    elif p >= 60:
        bg, tc, lbl = "#fef3c7", "#92400e", "Moderate"
    else:
        bg, tc, lbl = "#fee2e2", "#dc2626", "At Risk"
    return dmc.Paper([
        html.Div(icon, style={"fontSize": "22px", "textAlign": "center", "marginBottom": "8px"}),
        html.Div(name, style={
            "fontSize": "11px", "fontWeight": "700", "color": "#1e293b",
            "textAlign": "center", "marginBottom": "8px",
        }),
        html.Div(style={
            "width": "72px", "height": "72px", "borderRadius": "50%",
            "background": f"conic-gradient({col} {p:.1f}%, #e2e8f0 0)",
            "display": "flex", "alignItems": "center", "justifyContent": "center",
            "margin": "0 auto 10px",
        }, children=[
            html.Div(style={
                "width": "52px", "height": "52px", "borderRadius": "50%",
                "background": "#fff", "display": "flex",
                "alignItems": "center", "justifyContent": "center",
            }, children=[
                html.Span(f"{score:.0f}", style={
                    "fontSize": "16px", "fontWeight": "800", "color": col,
                }),
            ]),
        ]),
        html.Span(lbl, style={
            "display": "inline-block", "fontSize": "9px", "fontWeight": "700",
            "padding": "2px 8px", "borderRadius": "99px",
            "background": bg, "color": tc,
            "textTransform": "uppercase", "letterSpacing": ".05em",
        }),
    ], withBorder=True, radius="md", shadow="xs", p="md",
    style={"textAlign": "center", "transition": "box-shadow .2s"})


def _commodity_card(label: str, availability: float, icon: str, category: str) -> dmc.Paper:
    if availability >= 80:
        bar_color, risk_label, risk_bg, risk_color = "#16a34a", "✓ Adequate stock", "#dcfce7", "#15803d"
    elif availability >= 60:
        bar_color, risk_label, risk_bg, risk_color = "#d97706", "⚠ Watch level", "#fef3c7", "#92400e"
    else:
        bar_color, risk_label, risk_bg, risk_color = "#dc2626", "● Critical shortage", "#fee2e2", "#dc2626"
    return dmc.Paper([
        html.Div([
            html.Div(icon, style={
                "width": "36px", "height": "36px", "borderRadius": "9px",
                "background": "#f0fdf4", "display": "flex", "alignItems": "center",
                "justifyContent": "center", "fontSize": "18px", "flexShrink": "0",
            }),
            html.Div([
                html.Div(label, style={"fontSize": "12px", "fontWeight": "700", "color": "#0f172a"}),
                html.Div(category, style={"fontSize": "10px", "color": "#64748b"}),
            ]),
        ], style={"display": "flex", "alignItems": "center", "gap": "10px", "marginBottom": "12px"}),
        html.Div(f"{availability:.0f}%", style={
            "fontSize": "26px", "fontWeight": "800", "color": bar_color,
            "letterSpacing": "-.03em", "marginBottom": "2px",
        }),
        html.Div("Facilities with stock available", style={"fontSize": "11px", "color": "#64748b", "marginBottom": "8px"}),
        html.Div(html.Div(style={
            "width": f"{availability:.0f}%", "height": "100%",
            "background": bar_color, "borderRadius": "3px", "transition": "width .6s ease",
        }), style={"height": "6px", "background": "#f1f5f9", "borderRadius": "3px", "overflow": "hidden", "marginBottom": "6px"}),
        html.Span(risk_label, style={
            "fontSize": "10px", "fontWeight": "700", "padding": "2px 8px",
            "borderRadius": "99px", "display": "inline-flex", "alignItems": "center",
            "background": risk_bg, "color": risk_color,
        }),
    ], withBorder=True, radius="md", shadow="xs", p="md",
    style={"borderColor": "#e2e8f0", "transition": "box-shadow .2s"})


def _shipment_row(icon: str, icon_bg: str, name: str, detail: str, status: str) -> html.Div:
    _STATUS = {
        "Delivered": {"bg": "#dcfce7", "col": "#15803d", "label": "✓ Delivered"},
        "In transit": {"bg": "#fef3c7", "col": "#92400e", "label": "⟳ In Transit"},
        "Pending":    {"bg": "#fee2e2", "col": "#dc2626",  "label": "● Pending"},
    }
    s = _STATUS.get(status, {"bg": "#f1f5f9", "col": "#64748b", "label": status})
    return html.Div([
        html.Div(icon, style={
            "width": "36px", "height": "36px", "borderRadius": "9px",
            "background": icon_bg, "display": "flex", "alignItems": "center",
            "justifyContent": "center", "fontSize": "18px", "flexShrink": "0",
        }),
        html.Div([
            html.Div(name,   style={"fontSize": "12px", "fontWeight": "700", "color": "#0f172a"}),
            html.Div(detail, style={"fontSize": "11px", "color": "#64748b", "marginTop": "1px"}),
        ], style={"flex": "1", "minWidth": "0"}),
        html.Span(s["label"], style={
            "fontSize": "10px", "fontWeight": "800",
            "padding": "3px 10px", "borderRadius": "99px",
            "background": s["bg"], "color": s["col"], "flexShrink": "0",
        }),
    ], style={
        "display": "flex", "alignItems": "center", "gap": "12px",
        "padding": "12px 14px", "borderRadius": "10px",
        "border": "1px solid #e2e8f0", "background": "#fff",
        "marginBottom": "8px", "transition": "box-shadow .15s",
    })


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
        fig.add_trace(go.Scatter(
            x=series["month"],
            y=series["value"],
            mode="lines",
            line=dict(color=color, width=2.2, shape="spline", smoothing=1.0),
            fill="tozeroy",
            fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08)"
                      if color.startswith("#") and len(color) == 7 else "rgba(21,128,61,0.08)",
            hoverinfo="skip",
        ))
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
            **_EXEC_CHART_LAYOUT,
            height=260,
            annotations=[dict(text="No trend data available", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=12, color=MUTED))],
        )
        return fig

    smoothed, _ = _moving_average_values(series["value"].tolist(), "monthly")
    r = int(color[1:3], 16) if color.startswith("#") and len(color) == 7 else 21
    g_v = int(color[3:5], 16) if color.startswith("#") and len(color) == 7 else 128
    b = int(color[5:7], 16) if color.startswith("#") and len(color) == 7 else 61
    fig.add_trace(go.Scatter(
        x=series["month"],
        y=series["value"],
        name="Actual",
        mode="lines+markers",
        line=dict(color=color, width=2.2, shape="spline", smoothing=1.0),
        marker=dict(size=5, color=color, line=dict(color="#fff", width=1.2)),
        fill="tozeroy",
        fillcolor=f"rgba({r},{g_v},{b},0.07)",
    ))
    fig.add_trace(go.Scatter(
        x=series["month"],
        y=smoothed,
        name="3-mo avg",
        mode="lines",
        line=dict(color=color, width=1.5, dash="dot"),
        opacity=0.6,
        showlegend=True,
    ))
    if target is not None:
        fig.add_hline(
            y=target,
            line=dict(color="#f59e0b", width=1.4, dash="dash"),
            annotation_text="Target",
            annotation_font=dict(color="#f59e0b", size=10),
            annotation_position="right",
        )
    fig.update_layout(
        **_EXEC_CHART_LAYOUT,
        height=260,
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
    is_up = delta_value >= 0
    prefix = "+" if delta_value > 0 else ""
    delta_label = f"{prefix}{delta_value:.1f}%"
    delta_style = {
        "fontSize": "10px", "fontWeight": "800",
        "padding": "2px 7px", "borderRadius": "99px",
        "background": "#dcfce7" if is_up else "#fee2e2",
        "color": "#15803d" if is_up else "#dc2626",
    }
    val_str = f"{int(value):,}" if isinstance(value, (int, float)) and float(value).is_integer() else f"{value:,.1f}"
    return dmc.Paper(
        withBorder=True,
        radius="md",
        p="md",
        style={
            "background": "#fff",
            "borderColor": "#e2e8f0",
            "borderTop": f"3px solid {color}",
            "height": "100%",
            "transition": "box-shadow .2s",
        },
        children=[
            html.Div([
                html.Span(title, style={
                    "fontSize": "10px", "fontWeight": "700", "color": "#64748b",
                    "textTransform": "uppercase", "letterSpacing": ".06em",
                }),
                html.Span(delta_label, style=delta_style),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "marginBottom": "8px"}),
            html.Div(val_str, style={
                "fontSize": "24px", "fontWeight": "800", "color": "#0f172a",
                "letterSpacing": "-.03em", "lineHeight": "1",
            }),
            html.Div(note, style={"fontSize": "11px", "color": "#94a3b8", "marginTop": "3px"}),
            dcc.Graph(
                figure=_sparkline_figure(series, color),
                config={"displayModeBar": False, "responsive": True},
                style={"height": "44px", "marginTop": "8px"},
            ),
        ],
    )


_MORTALITY_TOKENS = {
    "Maternal Deaths":  {"accent": "#e11d48", "bg": "#fff1f2", "bdr": "#fecdd3", "shadow_rgba": "225,29,72"},
    "Neonatal Deaths":  {"accent": "#d97706", "bg": "#fffbeb", "bdr": "#fde68a", "shadow_rgba": "217,119,6"},
    "Stillbirths":      {"accent": "#7c3aed", "bg": "#f5f3ff", "bdr": "#ddd6fe", "shadow_rgba": "124,58,237"},
}


def _mortality_card(title: str, count: int, rate_label: str, rate_value: float, delta_count: int, color: str, background: str):
    tokens = _MORTALITY_TOKENS.get(title, {"accent": color, "bg": background, "bdr": color, "shadow_rgba": "0,0,0"})
    accent = tokens["accent"]
    delta_prefix = "+" if delta_count > 0 else ""
    delta_label = f"{delta_prefix}{delta_count:,}"
    is_worse = delta_count > 0
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
            html.Div(f"{count:,}", style={
                "fontSize": "36px", "fontWeight": "800", "letterSpacing": "-.04em",
                "color": accent, "lineHeight": "1", "marginBottom": "6px",
            }),
            html.Span(delta_label, style={
                "fontSize": "11px", "fontWeight": "700", "padding": "3px 9px",
                "borderRadius": "99px",
                "background": f"rgba({tokens['shadow_rgba']},.12)",
                "color": accent, "display": "inline-block", "marginBottom": "14px",
            }),
            html.Hr(style={"border": "none", "borderTop": "1px solid rgba(0,0,0,.07)", "margin": "10px 0"}),
            html.Div([
                html.Div([
                    html.Div(rate_label, style={"fontSize": "10px", "color": "#64748b", "marginBottom": "2px"}),
                    html.Div(f"{rate_value:,.1f}", style={"fontSize": "12px", "fontWeight": "700", "color": "#0f172a"}),
                ]),
                html.Div([
                    html.Div("vs. last period", style={"fontSize": "10px", "color": "#64748b", "marginBottom": "2px"}),
                    html.Div(
                        f"{'▲' if is_worse else '▼'} {delta_label}",
                        style={"fontSize": "12px", "fontWeight": "700", "color": "#dc2626" if is_worse else "#16a34a"},
                    ),
                ]),
            ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"}),
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
    fig.update_layout(
        **_EXEC_CHART_LAYOUT,
        barmode="stack",
        height=290,
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
    fig.update_layout(
        **_EXEC_CHART_LAYOUT,
        height=250,
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
    districts_covered = int(df["District"].dropna().astype(str).nunique()) if "District" in df.columns else 0

    kpi_specs = [
        ("Total Admissions",   "total_admissions",   ADMISSIONS_BLUE, "12-month reporting window", pd.Series(True, index=df.index)),
        ("Maternal Admissions","maternal_admissions", PRIMARY_GREEN,   "ANC, labour, and PNC",      _service_mask(df, ["ANC", "Labour", "PNC"])),
        ("Neonatal Admissions","neonatal_admissions", NEONATAL_ORANGE, "Neonatal care service area", _service_mask(df, ["Newborn"])),
        ("Total Deliveries",   "total_deliveries",    "#7C3AED",        "Labour encounters",          _service_mask(df, ["Labour"])),
        ("Live Births",        "live_births",         PRIMARY_GREEN,   "Outcome = live birth",       _contains_mask(df, "obs_value_coded", ["Live birth", "Live births", "Alive"])),
        ("Total Births",       "total_births",        STILLBIRTH_BLUE, "Live births + stillbirths",  _contains_mask(df, "concept_name", ["Outcome of the delivery", "Status of baby", "Admission outcome"])),
    ]

    kpi_cards = []
    for label, key, color, note, mask in kpi_specs:
        series = _monthly_series(df, mask if len(df) else pd.Series(dtype=bool),
                                 "encounter_id" if key.endswith("admissions") or key == "total_deliveries" else "person_id")
        delta = _delta_percent(current_metrics[key], previous_metrics[key])
        kpi_cards.append(_kpi_card(label, current_metrics[key], delta, series, color, note))

    mortality_specs = [
        ("Maternal Deaths", current_metrics["maternal_deaths"], "MMR per 100k live births",   current_metrics["institutional_mmr"],      current_metrics["maternal_deaths"]  - previous_metrics["maternal_deaths"],  MORTALITY_ROSE,   "#FFF1F2"),
        ("Neonatal Deaths", current_metrics["neonatal_deaths"], "NMR per 1,000 live births",  current_metrics["neonatal_mortality_rate"], current_metrics["neonatal_deaths"] - previous_metrics["neonatal_deaths"],   NEONATAL_ORANGE, "#FFF8EB"),
        ("Stillbirths",     current_metrics["stillbirths"],     "SBR per 1,000 total births", current_metrics["stillbirth_rate"],        current_metrics["stillbirths"]     - previous_metrics["stillbirths"],       STILLBIRTH_BLUE, "#EFF6FF"),
    ]

    admissions_series     = _monthly_series(df, pd.Series(True, index=df.index), "encounter_id")
    maternal_death_series = _monthly_series(df, _yn_mask(df, "mnid_pnc_maternal_death"), "person_id")
    neonatal_death_series = _monthly_series(df, _contains_mask(df, "obs_value_coded", ["Died", "Dead", "Death", "Neonatal death"]), "person_id")
    stillbirth_series     = _monthly_series(df, _yn_mask(df, "mnid_labour_stillbirth"), "person_id")

    geography_df = pd.DataFrame()
    region_rows: list[tuple[str, int]] = []
    if not df.empty and "District" in df.columns:
        geo_work = df.copy()
        geo_work["region"] = geo_work["District"].map(lambda x: DISTRICT_REGION_ZONE.get(str(x), ("Unknown", "Unknown"))[0])
        geo_group = geo_work.groupby("District", as_index=False).agg(
            maternal=("mnid_pnc_maternal_death",  lambda s: s.fillna("").astype(str).str.lower().isin({"yes", "true", "1"}).sum() if len(s) else 0),
            neonatal=("obs_value_coded",           lambda s: s.fillna("").astype(str).str.lower().isin({"died", "dead", "death", "neonatal death"}).sum() if len(s) else 0),
            stillbirth=("mnid_labour_stillbirth",  lambda s: s.fillna("").astype(str).str.lower().isin({"yes", "true", "1"}).sum() if len(s) else 0),
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

    hotspot_rows = [(row["District"], int(row["total"])) for _, row in geography_df.iterrows()] if not geography_df.empty else []

    explorer_specs = [
        ("Maternal deaths", MORTALITY_ROSE,   geography_df.assign(value=geography_df["maternal"])  if not geography_df.empty else pd.DataFrame(), maternal_death_series),
        ("Neonatal deaths", NEONATAL_ORANGE,  geography_df.assign(value=geography_df["neonatal"])  if not geography_df.empty else pd.DataFrame(), neonatal_death_series),
        ("Stillbirths",     STILLBIRTH_BLUE,  geography_df.assign(value=geography_df["stillbirth"]) if not geography_df.empty else pd.DataFrame(), stillbirth_series),
    ]

    explorer_tabs = dcc.Tabs(
        value="Maternal deaths",
        className="mnid-exec-subtabs",
        children=[
            dcc.Tab(
                label=label, value=label,
                className="mnid-exec-subtab",
                selected_className="mnid-exec-subtab--selected",
                children=html.Div(style={"paddingTop": "18px"}, children=[
                    dmc.SimpleGrid(cols=2, spacing="lg", children=[
                        dcc.Graph(figure=_mortality_distribution_chart(dist_df[["District", "value"]] if not dist_df.empty else pd.DataFrame(), f"{label} distribution", color), config={"displayModeBar": False}),
                        dcc.Graph(figure=_moving_average_chart(series_df, f"{label[:-1]} trend", color, None), config={"displayModeBar": False}),
                    ]),
                ]),
            )
            for label, color, dist_df, series_df in explorer_specs
        ],
    )

    # ---------- Hero section ----------
    hero_stats = [
        ("Total Admissions",    f"{current_metrics['total_admissions']:,}",   f"↑ {_delta_percent(current_metrics['total_admissions'], previous_metrics['total_admissions']):.1f}% vs prior"),
        ("Facility Deliveries", f"{current_metrics['facility_deliveries']:,}", f"↑ {_delta_percent(current_metrics['facility_deliveries'], previous_metrics['facility_deliveries']):.1f}% vs prior"),
        ("Live Births",         f"{current_metrics['live_births']:,}",         f"↑ {_delta_percent(current_metrics['live_births'], previous_metrics['live_births']):.1f}% vs prior"),
        ("Districts Covered",   f"{districts_covered} / 28",                   "✓ Full coverage" if districts_covered >= 28 else f"{districts_covered} reporting"),
    ]

    hero = html.Div([
        html.Div("National Health Situation Room", style={
            "fontSize": "10px", "fontWeight": "700", "color": "#4ade80",
            "letterSpacing": ".12em", "textTransform": "uppercase",
            "marginBottom": "8px", "display": "flex", "alignItems": "center", "gap": "7px",
        }),
        html.H1([
            "Maternal & Newborn Health ", html.Br(),
            html.Span("Intelligence Platform", style={"color": "#4ade80"}),
        ], style={
            "fontSize": "26px", "fontWeight": "800", "color": "#fff",
            "letterSpacing": "-.04em", "lineHeight": "1.15", "marginBottom": "5px",
        }),
        html.P(f"Malawi National Overview · {indicator_label} · Evidence for Action · Decision Support", style={
            "fontSize": "13px", "color": "rgba(255,255,255,0.6)", "marginBottom": "16px",
        }),
        html.Div([
            html.Span("● Live", style={
                "background": "rgba(74,222,128,.18)", "border": "1px solid rgba(74,222,128,.3)",
                "color": "#4ade80", "fontSize": "10px", "fontWeight": "700",
                "padding": "3px 10px", "borderRadius": "99px",
            }),
            html.Span(f"📅 {period_label}", style={
                "background": "rgba(255,255,255,.1)", "border": "1px solid rgba(255,255,255,.15)",
                "color": "rgba(255,255,255,.8)", "fontSize": "10px", "fontWeight": "700",
                "padding": "3px 10px", "borderRadius": "99px",
            }),
            html.Span(f"{districts_covered} Districts · {facilities_reporting} Facilities", style={
                "background": "rgba(255,255,255,.1)", "border": "1px solid rgba(255,255,255,.15)",
                "color": "rgba(255,255,255,.8)", "fontSize": "10px", "fontWeight": "700",
                "padding": "3px 10px", "borderRadius": "99px",
            }),
        ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "24px"}),
        html.Div([
            *[html.Div([
                html.Div(lbl, style={"fontSize": "9px", "color": "rgba(255,255,255,.45)", "textTransform": "uppercase", "letterSpacing": ".08em", "marginBottom": "4px"}),
                html.Div(val, style={"fontSize": "18px", "fontWeight": "700", "color": "#fff", "letterSpacing": "-.02em"}),
                html.Div(sub, style={"fontSize": "10px", "color": "rgba(255,255,255,.4)", "marginTop": "2px"}),
            ], style={"background": "rgba(255,255,255,.06)", "padding": "14px 18px"})
            for lbl, val, sub in hero_stats],
        ], style={
            "display": "grid", "gridTemplateColumns": "repeat(4,1fr)",
            "gap": "1px", "background": "rgba(255,255,255,.1)",
            "border": "1px solid rgba(255,255,255,.1)", "borderRadius": "10px", "overflow": "hidden",
        }),
    ], style={
        "background": "linear-gradient(135deg,#0a1f12 0%,#0f2f1a 30%,#15803d 72%,#16a34a 100%)",
        "borderRadius": "18px", "padding": "36px 40px",
        "marginBottom": "20px", "position": "relative", "overflow": "hidden",
    })

    # ---------- Alert banner ----------
    alert = None
    if current_metrics["maternal_deaths"] > 0:
        alert = _exec_alert_banner(
            f"Maternal deaths: {current_metrics['maternal_deaths']:,} recorded this period. "
            f"MMR: {current_metrics['institutional_mmr']:.1f} per 100k live births. Immediate review recommended."
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
            html.Span(f"{current_metrics['completeness']:.1f}%", style={"fontSize": "11px", "fontWeight": "600", "color": "#0f172a"}),
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
            _section_header("Data Volume · 12-Month Period"),
            dmc.SimpleGrid(cols=3, spacing="lg", mb="lg", children=kpi_cards),
            _section_header("Mortality Snapshot · Immediate Attention Required"),
            dmc.SimpleGrid(cols=3, spacing="md", mb="lg", children=[_mortality_card(*spec) for spec in mortality_specs]),
            _section_header("National Trends · 12-Month Run Charts"),
            dmc.SimpleGrid(cols=2, spacing="lg", mb="lg", children=[
                dmc.Paper(withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden", "borderColor": "#e2e8f0"},
                    children=[dcc.Graph(figure=_moving_average_chart(admissions_series, "Admissions trend", ADMISSIONS_BLUE, None), config={"displayModeBar": False})]),
                dmc.Paper(withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden", "borderColor": "#e2e8f0"},
                    children=[dcc.Graph(figure=_moving_average_chart(maternal_death_series, "Maternal death trend", MORTALITY_ROSE, None), config={"displayModeBar": False})]),
                dmc.Paper(withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden", "borderColor": "#e2e8f0"},
                    children=[dcc.Graph(figure=_moving_average_chart(neonatal_death_series, "Neonatal death trend", NEONATAL_ORANGE, None), config={"displayModeBar": False})]),
                dmc.Paper(withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden", "borderColor": "#e2e8f0"},
                    children=[dcc.Graph(figure=_moving_average_chart(stillbirth_series, "Stillbirth trend", STILLBIRTH_BLUE, None), config={"displayModeBar": False})]),
            ]),
            _section_header("Where is Mortality Happening? · Geographic Breakdown"),
            dmc.SimpleGrid(cols=2, spacing="lg", mb="lg", children=[
                _ranking_list("Region ranking · maternal deaths", region_rows or [("No data", 0)], [MORTALITY_ROSE, "#FB7185", "#FCA5A5", "#FECACA"]),
                dmc.Paper(withBorder=True, radius="md", p="md", style={"borderColor": "#e2e8f0"}, children=[
                    html.Div("District ranking · all mortality", style={"fontSize": "13px", "fontWeight": "700", "color": "#0f172a", "marginBottom": "10px"}),
                    dcc.Graph(figure=_stacked_mortality_chart(geography_df), config={"displayModeBar": False}),
                ]),
            ]),
            dmc.SimpleGrid(cols=2, spacing="lg", mb="lg", children=[
                _ranking_list("Facility hotspots", hotspot_rows or [("No data", 0)], [MORTALITY_ROSE, "#FB7185", "#FDA4AF", "#FCD34D"]),
                dmc.Paper(withBorder=True, radius="md", p="md", style={"borderColor": "#e2e8f0"}, children=[
                    html.Div("Zone comparison", style={"fontSize": "13px", "fontWeight": "700", "color": "#0f172a", "marginBottom": "6px"}),
                    html.P("Derived from district mortality distribution in the current scope.", style={"fontSize": "11px", "color": "#64748b", "marginTop": "4px"}),
                ]),
            ]),
            _section_header("Mortality Explorer · Interactive"),
            dmc.Paper(withBorder=True, radius="md", p="md", style={"borderColor": "#e2e8f0"}, children=[explorer_tabs]),
        ],
    )


def _readiness_bar(value: float, color: str) -> html.Div:
    return html.Div(
        style={"height": "8px", "background": GRID_C, "borderRadius": "999px", "overflow": "hidden"},
        children=[html.Div(style={"width": f"{max(min(value, 100), 0)}%", "height": "100%", "background": color, "borderRadius": "999px"})],
    )


def _readiness_status(value: float) -> tuple[str, str]:
    if value >= 75:
        return "Ready", SUCCESS_GREEN
    if value >= 55:
        return "Watch", WARNING_AMBER
    return "Support", MORTALITY_ROSE


def _readiness_indicator_rows(df: pd.DataFrame, indicators: list[dict]) -> list[dict]:
    rows = []
    for ind in indicators or []:
        num, den, pct = _cov(df, ind.get("numerator_filters", {}), ind.get("denominator_filters", {}))
        rows.append({
            "label": ind.get("label", "Indicator"),
            "num": num,
            "den": den,
            "pct": pct,
            "target": ind.get("target_pct") or ind.get("target") or 0,
        })
    return rows


def _mean_pct(rows: list[dict]) -> float:
    valid = [row["pct"] for row in rows if row.get("den", 0) > 0]
    if not valid:
        return 0.0
    return round(sum(valid) / len(valid), 1)


def _score_series_by_month(df: pd.DataFrame, indicators: list[dict], months: int = 6) -> list[dict]:
    if df.empty or "Date" not in df.columns or not indicators:
        return []
    periods = pd.to_datetime(df["Date"], errors="coerce").dt.to_period("M")
    recent = sorted(periods.dropna().unique())[-months:]
    rows = []
    for period in recent:
        period_df = df.loc[periods == period]
        indicator_rows = _readiness_indicator_rows(period_df, indicators)
        rows.append({
            "month": pd.Period(period, "M").strftime("%b %y"),
            "meeting": _mean_pct(indicator_rows),
            "support": round(max(100 - _mean_pct(indicator_rows), 0), 1),
        })
    return rows


def _entity_readiness_scores(df: pd.DataFrame, group_col: str, indicators: list[dict]) -> pd.DataFrame:
    if df.empty or group_col not in df.columns or not indicators:
        return pd.DataFrame(columns=[group_col, "national_score"])
    rows = []
    for entity, entity_df in df.groupby(group_col):
        score = _mean_pct(_readiness_indicator_rows(entity_df, indicators))
        rows.append({group_col: entity, "national_score": score})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("national_score", ascending=False).reset_index(drop=True)


def _facility_readiness_scores(df: pd.DataFrame, indicators: list[dict]) -> pd.DataFrame:
    if df.empty or "Facility_CODE" not in df.columns or "Facility" not in df.columns or not indicators:
        return pd.DataFrame(columns=["Facility_CODE", "Facility", "District", "national_score"])
    rows = []
    group_cols = ["Facility_CODE", "Facility"] + (["District"] if "District" in df.columns else [])
    for keys, facility_df in df.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        score = _mean_pct(_readiness_indicator_rows(facility_df, indicators))
        row = {
            "Facility_CODE": keys[0],
            "Facility": keys[1] if len(keys) > 1 else keys[0],
            "national_score": score,
        }
        if "District" in df.columns:
            row["District"] = keys[2] if len(keys) > 2 else ""
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("national_score", ascending=False).reset_index(drop=True)


def render_operational_readiness(
    df: pd.DataFrame,
    supply_inds: list[dict] | None = None,
    wf_inds: list[dict] | None = None,
    dq_inds: list[dict] | None = None,
) -> html.Div:
    readiness_inds = list(wf_inds or []) + list(supply_inds or []) + list(dq_inds or [])
    workforce_rows = _readiness_indicator_rows(df, list(wf_inds or []))
    supply_rows    = _readiness_indicator_rows(df, list(supply_inds or []))
    dq_rows        = _readiness_indicator_rows(df, list(dq_inds or []))
    all_rows       = _readiness_indicator_rows(df, readiness_inds)

    facility_df  = _facility_readiness_scores(df, readiness_inds)
    district_df  = _entity_readiness_scores(df, "District", readiness_inds)
    trend_rows   = _score_series_by_month(df, readiness_inds)

    national_score     = _mean_pct(all_rows)
    workforce_score    = _mean_pct(workforce_rows)
    supply_score       = _mean_pct(supply_rows)
    dq_score           = _mean_pct(dq_rows)
    facilities_assessed = int(df["Facility_CODE"].dropna().astype(str).nunique()) if "Facility_CODE" in df.columns else 0
    facilities_ready    = int((facility_df["national_score"] >= 75).sum()) if not facility_df.empty else 0
    need_support        = max(facilities_assessed - facilities_ready, 0)
    indicators_with_data = len([row for row in all_rows if row["den"] > 0])
    critical_count       = int((facility_df["national_score"] < 50).sum()) if not facility_df.empty else 0

    # ---------- Charts ----------
    workforce_chart = go.Figure()
    if not district_df.empty and workforce_rows:
        workforce_chart.add_trace(go.Bar(
            x=district_df["national_score"].round(1),
            y=district_df["District"],
            orientation="h",
            marker=dict(color=PRIMARY_GREEN, line=dict(width=0)),
        ))
        workforce_chart.update_layout(**_EXEC_CHART_LAYOUT, height=250)
        workforce_chart.update_layout(
            xaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False, showline=False,
                       tickfont=dict(size=10, color="#94a3b8"), ticksuffix="%"),
            yaxis=dict(showgrid=False, zeroline=False, showline=False, autorange="reversed",
                       tickfont=dict(size=10, color="#94a3b8")),
        )

    assessment_chart = go.Figure()
    if trend_rows:
        trend_df = pd.DataFrame(trend_rows)
        assessment_chart.add_trace(go.Bar(x=trend_df["month"], y=trend_df["meeting"], name="Readiness score", marker_color="#22c55e", marker_line_width=0))
        assessment_chart.add_trace(go.Bar(x=trend_df["month"], y=trend_df["support"],  name="Gap to 100%",    marker_color="#fca5a5", marker_line_width=0))
        assessment_chart.update_layout(**_EXEC_CHART_LAYOUT, barmode="stack", height=260)

    district_rank_chart = go.Figure()
    if not district_df.empty:
        colors = [PRIMARY_GREEN if v >= 60 else WARNING_AMBER if v >= 45 else MORTALITY_ROSE for v in district_df["national_score"]]
        district_rank_chart.add_trace(go.Bar(
            x=district_df["national_score"].round(1),
            y=district_df["District"],
            orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
        ))
        district_rank_chart.update_layout(**_EXEC_CHART_LAYOUT, height=250)
        district_rank_chart.update_layout(
            xaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False, showline=False,
                       tickfont=dict(size=10, color="#94a3b8"), ticksuffix="%"),
            yaxis=dict(showgrid=False, zeroline=False, showline=False, autorange="reversed",
                       tickfont=dict(size=10, color="#94a3b8")),
        )

    # ---------- Hero — National Readiness Command Center ----------
    bar_fill_pct = max(min(national_score, 100), 0)
    target_pct = 85
    hero = dmc.Paper(
        withBorder=True, radius="lg", shadow="xs", p="xl",
        style={"marginBottom": "22px", "borderColor": "#e2e8f0"},
        children=[
            html.Div("National Health System Readiness Command Center", style={
                "fontSize": "10px", "fontWeight": "700", "color": "#64748b",
                "textTransform": "uppercase", "letterSpacing": ".1em", "marginBottom": "16px",
            }),
            html.Div([
                # Score block
                html.Div([
                    html.Div("National Readiness Score", style={
                        "fontSize": "10px", "fontWeight": "700", "color": "#64748b",
                        "textTransform": "uppercase", "letterSpacing": ".09em", "marginBottom": "8px",
                    }),
                    html.Div([
                        html.Span(f"{national_score:.0f}", style={
                            "fontSize": "64px", "fontWeight": "900", "color": "#15803d",
                            "letterSpacing": "-.04em", "lineHeight": "1",
                        }),
                        html.Span("/100", style={"fontSize": "22px", "fontWeight": "500", "color": "#94a3b8"}),
                    ], style={"display": "flex", "alignItems": "flex-end", "gap": "4px"}),
                    html.Span(
                        "✓ Strong" if national_score >= 75 else "⚠ Moderate · Needs Improvement" if national_score >= 55 else "✕ At Risk · Urgent Action Required",
                        style={
                            "background": "#dcfce7" if national_score >= 75 else "#fef3c7" if national_score >= 55 else "#fee2e2",
                            "border": f"1px solid {'#bbf7d0' if national_score >= 75 else '#fde68a' if national_score >= 55 else '#fecaca'}",
                            "color": "#15803d" if national_score >= 75 else "#92400e" if national_score >= 55 else "#9f1239",
                            "fontSize": "10px", "fontWeight": "800",
                            "padding": "3px 10px", "borderRadius": "99px",
                            "display": "inline-block", "marginTop": "6px",
                        },
                    ),
                ], style={"flexShrink": "0"}),

                # Score bar
                html.Div([
                    html.Div([
                        html.Span("Score vs Target", style={"fontSize": "11px", "color": "#64748b"}),
                        html.Span(f"Target: {target_pct}", style={"fontSize": "11px", "color": "#d97706", "fontWeight": "700"}),
                    ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"}),
                    html.Div([
                        html.Div(style={
                            "height": "100%",
                            "width": f"{bar_fill_pct:.0f}%",
                            "background": "linear-gradient(90deg,#15803d,#4ade80)",
                            "borderRadius": "5px", "transition": "width .8s ease",
                        }),
                        html.Div(style={
                            "position": "absolute", "left": f"{target_pct}%", "top": "-3px", "bottom": "-3px",
                            "width": "2px", "background": "#dc2626", "borderRadius": "1px",
                        }),
                    ], style={"height": "10px", "background": "#f1f5f9", "borderRadius": "5px", "position": "relative", "overflow": "visible"}),
                ], style={"flex": "1", "minWidth": "200px", "alignSelf": "center"}),

                # Mini stat cards
                html.Div([
                    *[html.Div([
                        html.Div(lbl, style={"fontSize": "9px", "fontWeight": "700", "color": "#94a3b8", "textTransform": "uppercase", "letterSpacing": ".08em", "marginBottom": "4px"}),
                        html.Div(val, style={"fontSize": "22px", "fontWeight": "800", "letterSpacing": "-.03em", "color": col}),
                        html.Div(sub, style={"fontSize": "10px", "color": "#64748b", "marginTop": "2px"}),
                    ], style={"padding": "14px 20px", "borderRight": "1px solid #e2e8f0"})
                    for lbl, val, sub, col in [
                        ("Assessed",     f"{facilities_assessed:,}",  "All registered",        "#0f172a"),
                        ("Ready",        f"{facilities_ready:,}",      "≥75% readiness score",  "#16a34a"),
                        ("Need Support", f"{need_support:,}",          "Require intervention",  "#dc2626"),
                        ("Critical",     f"{critical_count:,}",        "<50% readiness",        "#d97706"),
                    ]],
                ], style={"display": "flex", "border": "1px solid #e2e8f0", "borderRadius": "10px", "overflow": "hidden"}),

            ], style={"display": "flex", "alignItems": "stretch", "gap": "32px", "flexWrap": "wrap"}),
        ],
    )

    # ---------- Domain ring cards ----------
    domain_rings = dmc.SimpleGrid(cols=4, spacing="lg", mb="lg", children=[
        _readiness_ring_card("👥", "Workforce",     workforce_score, "#15803d"),
        _readiness_ring_card("💊", "Commodities",   supply_score,    "#d97706"),
        _readiness_ring_card("🔧", "Equipment",     supply_score,    "#0284c7"),
        _readiness_ring_card("📊", "Data Quality",  dq_score,        "#7c3aed"),
    ])

    # ---------- Commodity cards ----------
    _COMMODITY_ICONS = ["💉", "🧪", "💊", "🩺"]
    _COMMODITY_CATS  = ["Injectable", "Lab supply", "Essential med", "Equipment"]
    commodity_grid_children = [
        _commodity_card(row["label"], row["pct"], _COMMODITY_ICONS[i % 4], _COMMODITY_CATS[i % 4])
        for i, row in enumerate(supply_rows[:4])
    ] or [dmc.Paper(withBorder=True, radius="md", p="md", children=[
        html.P("No live supply readiness observations in the current MNID source.", style={"fontSize": "12px", "color": "#64748b"}),
    ])]

    # ---------- Workforce domain score bars ----------
    workforce_summary = [
        ("Workforce score",    workforce_score, "#15803d"),
        ("Supply score",       supply_score,    "#d97706"),
        ("Data quality score", dq_score,        "#e11d48"),
        ("Overall readiness",  national_score,  "#2563eb"),
    ]

    # ---------- Procurement rows ----------
    procurement: list[dict] = []
    procurement_section: list = [html.P(
        "No procurement or distribution records are exposed in the current MNID source for this selection.",
        style={"fontSize": "12px", "color": "#64748b"},
    )]
    if procurement:
        _TONE_ICON = {"green": ("📦", "#f0fdf4"), "blue": ("🚚", "#eff6ff"), "amber": ("⏳", "#fffbeb")}
        procurement_section = [
            _shipment_row(
                *_TONE_ICON.get(item.get("tone", ""), ("📦", "#f8fafc")),
                f"{item['title']} — {item['detail']}",
                f"{item['note']} · {item['eta']}",
                item["status"],
            )
            for item in procurement
        ]

    return html.Div(
        className="mnid-executive-page",
        children=[
            hero,
            _section_header("Domain Readiness Overview"),
            domain_rings,
            _section_header("Workforce & Domain Score Summary"),
            dmc.SimpleGrid(cols=2, spacing="lg", mb="lg", children=[
                dmc.Paper(withBorder=True, radius="md", p="md", style={"borderColor": "#e2e8f0"}, children=[
                    html.Div("Domain scores", style={"fontSize": "13px", "fontWeight": "700", "color": "#0f172a", "marginBottom": "16px"}),
                    *[
                        html.Div([
                            html.Div(label, style={"fontSize": "12px", "color": "#64748b", "minWidth": "140px"}),
                            html.Div(html.Div(style={"width": f"{min(value,100):.0f}%", "height": "100%", "background": color, "borderRadius": "3px"}),
                                     style={"flex": "1", "height": "8px", "background": "#f1f5f9", "borderRadius": "3px", "overflow": "hidden", "margin": "0 12px"}),
                            html.Div(f"{value:.0f}%", style={"fontSize": "12px", "fontWeight": "700", "color": "#0f172a", "minWidth": "36px", "textAlign": "right"}),
                        ], style={"display": "flex", "alignItems": "center", "marginBottom": "14px"})
                        for label, value, color in workforce_summary
                    ],
                ]),
                dmc.Paper(withBorder=True, radius="md", p="md", style={"borderColor": "#e2e8f0"}, children=[
                    html.Div("District readiness by live MNID indicators", style={"fontSize": "13px", "fontWeight": "700", "color": "#0f172a", "marginBottom": "12px"}),
                    dcc.Graph(figure=workforce_chart, config={"displayModeBar": False}),
                ]),
            ]),
            _section_header("Commodity Availability · Essential Medicines"),
            dmc.SimpleGrid(cols=4, spacing="lg", mb="lg", children=commodity_grid_children),
            _section_header("Facility Assessments · Standards Compliance"),
            dmc.SimpleGrid(cols=2, spacing="lg", mb="lg", children=[
                dmc.Paper(withBorder=True, radius="md", p="md", style={"borderColor": "#e2e8f0"}, children=[
                    html.Div("Assessment summary", style={"fontSize": "13px", "fontWeight": "700", "color": "#0f172a", "marginBottom": "16px"}),
                    html.Div([
                        html.Div([
                            html.Div(f"{facilities_assessed:,}", style={"fontSize": "28px", "fontWeight": "800", "color": "#0f172a", "textAlign": "center"}),
                            html.Div("Assessed", style={"fontSize": "11px", "color": "#64748b", "textAlign": "center"}),
                        ], style={"padding": "14px", "background": "#f8fafc", "borderRadius": "10px"}),
                        html.Div([
                            html.Div(f"{facilities_ready:,}", style={"fontSize": "28px", "fontWeight": "800", "color": "#15803d", "textAlign": "center"}),
                            html.Div("Ready", style={"fontSize": "11px", "color": "#64748b", "textAlign": "center"}),
                        ], style={"padding": "14px", "background": "#f0fdf4", "borderRadius": "10px"}),
                        html.Div([
                            html.Div(f"{need_support:,}", style={"fontSize": "28px", "fontWeight": "800", "color": "#dc2626", "textAlign": "center"}),
                            html.Div("Need support", style={"fontSize": "11px", "color": "#64748b", "textAlign": "center"}),
                        ], style={"padding": "14px", "background": "#fee2e2", "borderRadius": "10px"}),
                    ], style={"display": "grid", "gridTemplateColumns": "repeat(3,1fr)", "gap": "10px", "marginBottom": "16px"}),
                    dcc.Graph(figure=assessment_chart, config={"displayModeBar": False}),
                ]),
                dmc.Paper(withBorder=True, radius="md", p="md", style={"borderColor": "#e2e8f0"}, children=[
                    html.Div("District compliance ranking", style={"fontSize": "13px", "fontWeight": "700", "color": "#0f172a", "marginBottom": "12px"}),
                    dcc.Graph(figure=district_rank_chart, config={"displayModeBar": False}),
                ]),
            ]),
            _section_header("Procurement & Distribution · Supply Chain Status"),
            html.Div(procurement_section),
        ],
    )
