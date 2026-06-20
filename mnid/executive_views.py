"""Executive Country Profile and Operational Readiness views for MNID."""
from __future__ import annotations

import dash_mantine_components as dmc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from mnid.chart_helpers import _cov, _moving_average_values, _grouped_filter_counts
from mnid.chart_helpers import (
    CHART_HEIGHT_MD, CHART_HEIGHT_LG,
    _graph_style, _graph_scroll_wrap, _clamp_chart_height,
)
from mnid.coverage import _system_readiness
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


def _run_chart(series: pd.DataFrame, title: str, color: str, y_title: str, target: float | None = None) -> go.Figure:
    fig = go.Figure()
    if series.empty:
        fig.update_layout(
            **_EXEC_CHART_LAYOUT,
            height=300,
            annotations=[dict(text="No trend data available", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=12, color=MUTED))],
        )
        return fig

    fig.add_trace(go.Scatter(
        x=series["month"],
        y=series["value"],
        name=title,
        mode="lines+markers",
        line=dict(color=color, width=2.4),
        marker=dict(size=5, color=color, line=dict(color="#fff", width=1.2)),
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
        height=300,
        xaxis=dict(
            showgrid=False,
            showline=False,
            zeroline=False,
            tickfont=dict(size=10, color="#94a3b8"),
            tickformat="%b %Y",
            title=dict(text="Month", font=dict(size=10, color="#64748b")),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#f1f5f9",
            gridwidth=1,
            showline=False,
            zeroline=False,
            tickfont=dict(size=10, color="#94a3b8"),
            title=dict(text=y_title, font=dict(size=10, color="#64748b")),
            rangemode="tozero",
        ),
    )
    return fig


def _multi_run_chart(series_df: pd.DataFrame, title: str, y_title: str, target: float | None = None) -> go.Figure:
    fig = go.Figure()
    if series_df.empty:
        fig.update_layout(
            **_EXEC_CHART_LAYOUT,
            height=300,
            annotations=[dict(text="No trend data available", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=12, color=MUTED))],
        )
        return fig

    for label in series_df["series"].dropna().unique():
        trace_df = series_df[series_df["series"] == label]
        color = trace_df["color"].iloc[0] if "color" in trace_df.columns and not trace_df.empty else PRIMARY_GREEN
        fig.add_trace(go.Scatter(
            x=trace_df["month"],
            y=trace_df["value"],
            name=label,
            mode="lines+markers",
            line=dict(color=color, width=2.2),
            marker=dict(size=5, color=color, line=dict(color="#fff", width=1.0)),
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
        height=300,
        xaxis=dict(
            showgrid=False,
            showline=False,
            zeroline=False,
            tickfont=dict(size=10, color="#94a3b8"),
            tickformat="%b %Y",
            title=dict(text="Month", font=dict(size=10, color="#64748b")),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#f1f5f9",
            gridwidth=1,
            showline=False,
            zeroline=False,
            tickfont=dict(size=10, color="#94a3b8"),
            title=dict(text=y_title, font=dict(size=10, color="#64748b")),
            rangemode="tozero",
        ),
    )
    return fig


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
            *([
                html.Div([
                    html.Div([
                        html.Span(label, style={"fontSize": "10px", "fontWeight": "700", "color": accent}),
                        html.Span(value, style={"fontSize": "10px", "color": "#334155"}),
                    ], style={
                        "padding": "6px 8px",
                        "background": "#fff",
                        "border": f"1px solid rgba({tokens['shadow_rgba']},.16)",
                        "borderRadius": "8px",
                    })
                    for label, value in breakdown
                ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px", "marginTop": "12px"})
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

    summary_cards = [
        _summary_card("Maternity Unit Admissions", f"{current_metrics['maternal_admissions']:,}", "ANC, labour, and PNC encounters", PRIMARY_GREEN),
        _summary_card("Neonatal Care Unit Admissions", f"{current_metrics['neonatal_admissions']:,}", "Newborn care encounters", NEONATAL_ORANGE),
        _summary_card("Total Births", f"{current_metrics['total_births']:,}", "Live births and stillbirths", STILLBIRTH_BLUE),
        _summary_card("Live Births", f"{current_metrics['live_births']:,}", "Outcome recorded as live birth", SUCCESS_GREEN),
        _summary_card("Stillbirths", f"{current_metrics['stillbirths']:,}", "Stillbirths in current reporting period", "#7C3AED"),
        _summary_card("Maternal Deaths", f"{current_metrics['maternal_deaths']:,}", "Deaths recorded in selected scope", MORTALITY_ROSE),
        _summary_card("Neonatal Deaths", f"{current_metrics['neonatal_deaths']:,}", "Deaths recorded in selected scope", WARNING_AMBER),
        _summary_card("Districts Covered", f"{districts_covered:,}", f"{facilities_reporting:,} facilities reporting", ADMISSIONS_BLUE),
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

    maternal_death_series = _monthly_series(df, _yn_mask(df, "mnid_pnc_maternal_death"), "person_id")
    neonatal_death_series = _monthly_series(df, _contains_mask(df, "obs_value_coded", ["Died", "Dead", "Death", "Neonatal death"]), "person_id")
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

    complication_specs = [
        ("Pre-eclampsia and Eclampsia", MORTALITY_ROSE, _yn_mask(df, "mnid_labour_eclampsia") | _contains_mask(df, "obs_value_coded", ["Pre-eclampsia", "Pre eclampsia", "Preeclampsia", "Eclampsia"])),
        ("Postpartum Haemorrhage", WARNING_AMBER, _yn_mask(df, "mnid_labour_pph")),
        ("Maternal Sepsis", "#B91C1C", _yn_mask(df, "mnid_labour_maternal_sepsis")),
        ("Obstructed or Prolonged Labour", "#7C3AED", _yn_mask(df, "mnid_labour_obstructed_labour") | _contains_mask(df, "obs_value_coded", ["Obstructed labour", "Prolonged labour", "Prolonged Labor"])),
        ("Ruptured Uterus", "#475569", _contains_mask(df, "obs_value_coded", ["Ruptured uterus", "Uterine rupture"])),
        ("Birth Asphyxia", "#D97706", _yn_mask(df, "mnid_newborn_birth_asphyxia")),
        ("Preterm Birth", PRIMARY_GREEN, _yn_mask(df, "mnid_labour_preterm")),
        ("Neonatal Sepsis", ADMISSIONS_BLUE, _yn_mask(df, "mnid_newborn_sepsis")),
    ]
    complication_cards = [
        dmc.Paper(withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden", "borderColor": "#e2e8f0"}, children=[
            dcc.Graph(figure=_run_chart(_monthly_series(df, mask, "person_id"), title, color, "Cases"), config={"displayModeBar": False}),
        ])
        for title, color, mask in complication_specs
    ]

    hero = dmc.Paper(
        withBorder=True,
        radius="lg",
        shadow="xs",
        p="xl",
        style={"marginBottom": "20px", "borderColor": "#e2e8f0"},
        children=[
            html.Div("Country Profile", style={
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
                    html.P(f"Malawi national overview · {indicator_label} · Evidence for action · Decision support", style={
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
            _section_header("Country Summary · Current Reporting Period"),
            _responsive_grid(summary_cards, min_width="200px", gap="14px"),
            _section_header("Mortality Snapshot · Immediate Attention Required"),
            _responsive_grid([_mortality_card(*spec) for spec in mortality_specs], min_width="260px", gap="14px"),
            _section_header("Mortality Trends · 12-Month Run Charts"),
            _responsive_grid([
                dmc.Paper(withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden", "borderColor": "#e2e8f0"},
                    children=[dcc.Graph(figure=_run_chart(total_births_series, "Total Births", PRIMARY_GREEN, "Births"), config={"displayModeBar": False})]),
                dmc.Paper(withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden", "borderColor": "#e2e8f0"},
                    children=[dcc.Graph(figure=_run_chart(maternal_death_series, "Maternal Mortality", MORTALITY_ROSE, "Deaths"), config={"displayModeBar": False})]),
                dmc.Paper(withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden", "borderColor": "#e2e8f0"},
                    children=[dcc.Graph(figure=_run_chart(neonatal_death_series, "Neonatal Mortality", NEONATAL_ORANGE, "Deaths"), config={"displayModeBar": False})]),
                dmc.Paper(withBorder=True, radius="md", shadow="xs", style={"overflow": "hidden", "borderColor": "#e2e8f0"},
                    children=[dcc.Graph(figure=_multi_run_chart(stillbirth_trend_series, "Stillbirths", "Cases"), config={"displayModeBar": False})]),
            ], min_width="320px", gap="18px"),
            _section_header("Complication Trends"),
            _responsive_grid(complication_cards, min_width="320px", gap="18px"),
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


def _readiness_scores_from_counts(keys: list, group_cols: list[str], indicators: list[dict], df: pd.DataFrame) -> dict:
    """Average per-indicator coverage % across `indicators` for each group key, skipping
    indicators with a zero denominator for that group (matches _mean_pct's behaviour)."""
    pct_by_key: dict = {k: [] for k in keys}
    for ind in indicators:
        num_counts = _grouped_filter_counts(df, group_cols, ind.get("numerator_filters", {}))
        den_counts = _grouped_filter_counts(df, group_cols, ind.get("denominator_filters", {}))
        for k in keys:
            lookup_k = k if len(group_cols) > 1 else k[0]
            den = int(den_counts.get(lookup_k, 0))
            if den <= 0:
                continue
            num = int(num_counts.get(lookup_k, 0))
            pct_by_key[k].append(round(min(num / den * 100, 100.0), 1))
    return {k: (round(sum(v) / len(v), 1) if v else 0.0) for k, v in pct_by_key.items()}


def _entity_readiness_scores(df: pd.DataFrame, group_col: str, indicators: list[dict]) -> pd.DataFrame:
    if df.empty or group_col not in df.columns or not indicators:
        return pd.DataFrame(columns=[group_col, "national_score"])
    keys = [(g,) for g in df[group_col].dropna().unique()]
    scores = _readiness_scores_from_counts(keys, [group_col], indicators, df)
    rows = [{group_col: k[0], "national_score": scores[k]} for k in keys]
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("national_score", ascending=False).reset_index(drop=True)


def _facility_readiness_scores(df: pd.DataFrame, indicators: list[dict]) -> pd.DataFrame:
    if df.empty or "Facility_CODE" not in df.columns or "Facility" not in df.columns or not indicators:
        return pd.DataFrame(columns=["Facility_CODE", "Facility", "District", "national_score"])
    group_cols = ["Facility_CODE", "Facility"] + (["District"] if "District" in df.columns else [])
    combos = df[group_cols].drop_duplicates()
    keys = [tuple(row) for row in combos.itertuples(index=False, name=None)]
    scores = _readiness_scores_from_counts(keys, group_cols, indicators, df)
    rows = []
    for k in keys:
        row = {"Facility_CODE": k[0], "Facility": k[1], "national_score": scores[k]}
        if "District" in group_cols:
            row["District"] = k[2]
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
    workforce_chart_inner_height = CHART_HEIGHT_MD
    workforce_chart_outer_height = CHART_HEIGHT_MD
    if not district_df.empty and workforce_rows:
        workforce_chart_inner_height = max(CHART_HEIGHT_MD, len(district_df) * 24 + 60)
        workforce_chart_outer_height = _clamp_chart_height(workforce_chart_inner_height, CHART_HEIGHT_MD, CHART_HEIGHT_LG)
        workforce_chart.add_trace(go.Bar(
            x=district_df["national_score"].round(1),
            y=district_df["District"],
            orientation="h",
            marker=dict(color=PRIMARY_GREEN, line=dict(width=0)),
        ))
        workforce_chart.update_layout(**_EXEC_CHART_LAYOUT, height=workforce_chart_inner_height)
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
        assessment_chart.update_layout(**_EXEC_CHART_LAYOUT, barmode="stack", height=CHART_HEIGHT_MD)

    district_rank_chart = go.Figure()
    district_rank_inner_height = CHART_HEIGHT_MD
    district_rank_outer_height = CHART_HEIGHT_MD
    if not district_df.empty:
        district_rank_inner_height = max(CHART_HEIGHT_MD, len(district_df) * 24 + 60)
        district_rank_outer_height = _clamp_chart_height(district_rank_inner_height, CHART_HEIGHT_MD, CHART_HEIGHT_LG)
        colors = [PRIMARY_GREEN if v >= 60 else WARNING_AMBER if v >= 45 else MORTALITY_ROSE for v in district_df["national_score"]]
        district_rank_chart.add_trace(go.Bar(
            x=district_df["national_score"].round(1),
            y=district_df["District"],
            orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
        ))
        district_rank_chart.update_layout(**_EXEC_CHART_LAYOUT, height=district_rank_inner_height)
        district_rank_chart.update_layout(
            xaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False, showline=False,
                       tickfont=dict(size=10, color="#94a3b8"), ticksuffix="%"),
            yaxis=dict(showgrid=False, zeroline=False, showline=False, autorange="reversed",
                       tickfont=dict(size=10, color="#94a3b8")),
        )

    # ---------- Hero - National Readiness Command Center ----------
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
            _section_header("System Readiness Detail"),
            _system_readiness(df, list(supply_inds or []), list(wf_inds or []), list(dq_inds or [])),
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
                    _graph_scroll_wrap(
                        dcc.Graph(
                            figure=workforce_chart,
                            config={"displayModeBar": False},
                            style=_graph_style(workforce_chart_inner_height),
                        ),
                        workforce_chart_outer_height,
                    ),
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
                    dcc.Graph(
                        figure=assessment_chart,
                        config={"displayModeBar": False},
                        style=_graph_style(CHART_HEIGHT_MD),
                    ),
                ]),
                dmc.Paper(withBorder=True, radius="md", p="md", style={"borderColor": "#e2e8f0"}, children=[
                    html.Div("District compliance ranking", style={"fontSize": "13px", "fontWeight": "700", "color": "#0f172a", "marginBottom": "12px"}),
                    _graph_scroll_wrap(
                        dcc.Graph(
                            figure=district_rank_chart,
                            config={"displayModeBar": False},
                            style=_graph_style(district_rank_inner_height),
                        ),
                        district_rank_outer_height,
                    ),
                ]),
            ]),
            _section_header("Procurement & Distribution · Supply Chain Status"),
            html.Div(procurement_section),
        ],
    )
