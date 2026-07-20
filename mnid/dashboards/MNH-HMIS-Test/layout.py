"""Country-profile-inspired visualizations for cached DHIS2 MNH indicators."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
from dash import dash_table, dcc, html

GREEN = "#15803D"
BLUE = "#2563EB"
AMBER = "#D97706"
RED = "#DC2626"
PURPLE = "#7C3AED"
TEAL = "#0F766E"
TEXT = "#0F172A"
MUTED = "#64748B"
BORDER = "#E2E8F0"
SURFACE = "#FFFFFF"
BACKGROUND = "#F8FAFC"
HERO = "#182136"

DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "dhis2" / "aggregates" / "hmis_test.parquet"
)

GROUP_ORDER = (
    "Births and outcomes",
    "Antenatal care",
    "Delivery and newborn care",
)
GROUP_COLORS = {
    "Births and outcomes": RED,
    "Antenatal care": GREEN,
    "Delivery and newborn care": BLUE,
    "Other indicators": PURPLE,
}
LEGACY_GROUPS = {
    "EVt2iC6Tn34": "Antenatal care",
    "gLN6hOgR6ra": "Antenatal care",
    "zAvhV81SCLV": "Antenatal care",
    "iBBnHx1Uf50": "Births and outcomes",
    "WjHvEHMCyKo": "Births and outcomes",
}
ADVERSE_OUTCOME_IDS = {
    "fresh_stillbirths", "macerated_stillbirths", "maternal_deaths",
    "neonatal_deaths", "stillbirths",
}


def _empty(message: str) -> html.Div:
    return html.Div(
        message,
        style={
            "padding": "28px",
            "background": SURFACE,
            "border": f"1px solid {BORDER}",
            "borderRadius": "14px",
            "color": MUTED,
        },
    )


def _load_sample(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()
    frame["period_start"] = pd.to_datetime(frame.get("period_start"), errors="coerce")
    frame["value"] = pd.to_numeric(frame.get("value"), errors="coerce")
    if "indicator_group" not in frame.columns:
        frame["indicator_group"] = frame["indicator_id"].map(LEGACY_GROUPS).fillna("Other indicators")
    return frame.dropna(subset=["period_start", "value"])


def _apply_scope(frame: pd.DataFrame, start_date, end_date, scope_meta: dict) -> pd.DataFrame:
    result = frame.copy()
    start = pd.to_datetime(start_date, errors="coerce")
    end = pd.to_datetime(end_date, errors="coerce")
    if not pd.isna(start):
        result = result[result["period_start"] >= start]
    if not pd.isna(end):
        result = result[result["period_start"] <= end]
    districts = {str(item) for item in scope_meta.get("selected_districts") or []}
    facilities = {str(item) for item in scope_meta.get("selected_facilities") or []}
    if facilities:
        result = result[
            result["org_unit_name"].astype(str).isin(facilities)
            | result["facility_code"].astype(str).isin(facilities)
            | result["org_unit_id"].astype(str).isin(facilities)
        ]
    elif districts:
        result = result[result["district"].astype(str).isin(districts)]
    return result


def _section_header(title: str, subtitle: str | None = None, color: str = GREEN) -> html.Div:
    return html.Div(
        [
            html.Div(style={
                "width": "4px", "height": "30px", "background": color,
                "borderRadius": "4px", "flexShrink": "0",
            }),
            html.Div([
                html.Div(title, style={
                    "fontSize": "14px", "fontWeight": 800, "color": TEXT,
                    "textTransform": "uppercase", "letterSpacing": ".06em",
                }),
                html.Div(subtitle, style={
                    "fontSize": "11px", "color": MUTED, "marginTop": "2px",
                }) if subtitle else None,
            ]),
        ],
        style={
            "display": "flex", "alignItems": "center", "gap": "10px",
            "margin": "24px 0 12px",
        },
    )


def _scope_label(scope_meta: dict, facility_count: int, district_count: int) -> str:
    facilities = scope_meta.get("selected_facilities") or []
    districts = scope_meta.get("selected_districts") or []
    if facilities:
        return facilities[0] if len(facilities) == 1 else f"{len(facilities)} selected facilities"
    if districts:
        return districts[0] if len(districts) == 1 else f"{len(districts)} selected districts"
    return f"National · {district_count} districts · {facility_count} reporting units"


def _hero(period_min: str, period_max: str, indicator_count: int, facility_count: int,
          district_count: int, scope_meta: dict) -> html.Div:
    pills = [
        ("Reporting period", f"{period_min} – {period_max}"),
        ("Active scope", _scope_label(scope_meta, facility_count, district_count)),
        ("Indicators", f"{indicator_count} verified indicators"),
        ("Source", "Malawi HMIS DHIS2 snapshot"),
    ]
    return html.Div(
        [
            html.Div("MNH HMIS COUNTRY PROFILE", style={
                "fontSize": "10px", "fontWeight": 800, "letterSpacing": ".13em",
                "color": "#86EFAC", "marginBottom": "7px",
            }),
            html.Div("Maternal & Newborn Health", style={
                "fontSize": "28px", "fontWeight": 850, "color": "#FFFFFF",
                "letterSpacing": "-.02em",
            }),
            html.Div(
                "Facility-reported aggregate performance from the latest controlled DHIS2 synchronization.",
                style={"fontSize": "12px", "color": "#CBD5E1", "marginTop": "5px"},
            ),
            html.Div([
                html.Div([
                    html.Div(label, style={
                        "fontSize": "9px", "fontWeight": 800, "color": "#94A3B8",
                        "textTransform": "uppercase", "letterSpacing": ".07em",
                    }),
                    html.Div(value, style={
                        "fontSize": "12px", "fontWeight": 700, "color": "#F8FAFC",
                        "marginTop": "3px",
                    }),
                ], style={
                    "background": "rgba(255,255,255,.07)",
                    "border": "1px solid rgba(255,255,255,.12)",
                    "borderRadius": "10px", "padding": "10px 12px", "minWidth": "180px",
                })
                for label, value in pills
            ], style={"display": "flex", "gap": "9px", "flexWrap": "wrap", "marginTop": "18px"}),
        ],
        style={
            "background": HERO, "borderRadius": "16px", "padding": "22px 24px",
            "boxShadow": "0 10px 24px rgba(15,23,42,.12)",
        },
    )


def _indicator_summary(frame: pd.DataFrame) -> pd.DataFrame:
    periods = sorted(frame["period_start"].dropna().unique())
    latest_period = periods[-1]
    previous_period = periods[-2] if len(periods) > 1 else None
    total = frame.groupby(
        ["indicator_id", "indicator_name", "indicator_group"], as_index=False
    )["value"].sum().rename(columns={"value": "total"})
    latest = (
        frame[frame["period_start"] == latest_period]
        .groupby("indicator_id", as_index=False)["value"].sum()
        .rename(columns={"value": "latest"})
    )
    if previous_period is None:
        previous = pd.DataFrame(columns=["indicator_id", "previous"])
    else:
        previous = (
            frame[frame["period_start"] == previous_period]
            .groupby("indicator_id", as_index=False)["value"].sum()
            .rename(columns={"value": "previous"})
        )
    units = (
        frame.groupby("indicator_id", as_index=False)["org_unit_id"]
        .nunique().rename(columns={"org_unit_id": "reporting_units"})
    )
    summary = total.merge(latest, on="indicator_id", how="left")
    summary = summary.merge(previous, on="indicator_id", how="left")
    summary = summary.merge(units, on="indicator_id", how="left")
    summary["change"] = summary.apply(
        lambda row: None if not row.get("previous") else
        ((row.get("latest", 0) - row["previous"]) / row["previous"]) * 100,
        axis=1,
    )
    return summary.sort_values(["indicator_group", "indicator_name"])


def _indicator_card(row, color: str) -> html.Div:
    change = row.change
    increase_is_adverse = row.indicator_id in ADVERSE_OUTCOME_IDS
    if pd.isna(change):
        change_label, change_color, change_bg = "No prior comparison", MUTED, "#F1F5F9"
    elif change > 0:
        change_label = f"▲ {change:.1f}% vs prior month"
        change_color = RED if increase_is_adverse else GREEN
        change_bg = "#FEE2E2" if increase_is_adverse else "#DCFCE7"
    elif change < 0:
        change_label = f"▼ {abs(change):.1f}% vs prior month"
        change_color = GREEN if increase_is_adverse else RED
        change_bg = "#DCFCE7" if increase_is_adverse else "#FEE2E2"
    else:
        change_label, change_color, change_bg = "● No monthly change", MUTED, "#F1F5F9"
    return html.Div(
        [
            html.Div(row.indicator_name, style={
                "fontSize": "11px", "fontWeight": 750, "color": TEXT,
                "lineHeight": "1.35", "minHeight": "30px",
            }),
            html.Div(f"{row.total:,.0f}", style={
                "fontSize": "25px", "fontWeight": 850, "color": color,
                "letterSpacing": "-.03em", "marginTop": "8px",
            }),
            html.Div("Selected-period total", style={
                "fontSize": "9px", "color": MUTED, "marginTop": "-2px",
            }),
            html.Div([
                html.Span(change_label, style={
                    "fontSize": "9px", "fontWeight": 750, "color": change_color,
                    "background": change_bg, "borderRadius": "99px", "padding": "3px 7px",
                }),
                html.Span(f"{int(row.reporting_units):,} units", style={
                    "fontSize": "9px", "color": MUTED,
                }),
            ], style={
                "display": "flex", "justifyContent": "space-between",
                "alignItems": "center", "gap": "6px", "marginTop": "12px",
            }),
        ],
        style={
            "background": SURFACE, "border": f"1px solid {BORDER}",
            "borderTop": f"3px solid {color}", "borderRadius": "12px",
            "padding": "13px", "boxShadow": "0 2px 8px rgba(15,23,42,.04)",
        },
    )


def _chart_card(title: str, subtitle: str, figure) -> html.Div:
    return html.Div(
        [
            html.Div(title, style={"fontSize": "14px", "fontWeight": 800, "color": TEXT}),
            html.Div(subtitle, style={"fontSize": "10px", "color": MUTED, "marginTop": "3px"}),
            dcc.Graph(
                figure=figure,
                config={"displayModeBar": False, "responsive": True},
                style={"height": "370px"},
            ),
        ],
        style={
            "background": SURFACE, "border": f"1px solid {BORDER}",
            "borderRadius": "14px", "padding": "16px",
            "boxShadow": "0 2px 10px rgba(15,23,42,.04)",
        },
    )


def _trend_figure(frame: pd.DataFrame, group: str, color: str):
    group_frame = frame[frame["indicator_group"] == group]
    trend = group_frame.groupby(
        ["period_start", "indicator_name"], as_index=False
    )["value"].sum()
    figure = px.line(
        trend, x="period_start", y="value", color="indicator_name", markers=True,
        labels={
            "period_start": "Reporting month", "value": "Reported value",
            "indicator_name": "Indicator",
        },
    )
    figure.update_traces(line={"width": 2}, marker={"size": 5})
    figure.update_layout(
        margin={"l": 35, "r": 15, "t": 20, "b": 35},
        legend={"orientation": "h", "y": -0.28, "font": {"size": 9}},
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        hovermode="x unified", colorway=[color, BLUE, AMBER, PURPLE, TEAL, RED, GREEN],
        font={"color": TEXT},
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="#EEF2F7")
    return figure


def _district_figure(frame: pd.DataFrame):
    priority_ids = ["maternal_deaths", "neonatal_deaths", "stillbirths"]
    priority = frame[frame["indicator_id"].isin(priority_ids)].copy()
    title = "Priority outcomes"
    if priority.empty:
        first_id = frame["indicator_id"].iloc[0]
        priority = frame[frame["indicator_id"] == first_id].copy()
        title = str(priority["indicator_name"].iloc[0])
    district = (
        priority.dropna(subset=["district"])
        .groupby("district", as_index=False)["value"].sum()
        .nlargest(15, "value").sort_values("value")
    )
    figure = px.bar(
        district, x="value", y="district", orientation="h",
        color_discrete_sequence=[RED],
        labels={"value": "Reported events", "district": "District"},
    )
    figure.update_layout(
        margin={"l": 25, "r": 15, "t": 20, "b": 35},
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE, font={"color": TEXT},
    )
    figure.update_xaxes(gridcolor="#EEF2F7")
    figure.update_yaxes(showgrid=False)
    return title, figure


def _facility_table(frame: pd.DataFrame):
    facility = (
        frame.groupby(
            ["org_unit_name", "district", "indicator_group", "indicator_name"],
            dropna=False, as_index=False,
        )["value"].sum().sort_values("value", ascending=False)
    )
    facility = facility.rename(columns={
        "org_unit_name": "Facility", "district": "District",
        "indicator_group": "Domain", "indicator_name": "Indicator", "value": "Value",
    })
    return dash_table.DataTable(
        data=facility.to_dict("records"),
        columns=[
            {"name": name, "id": name, "type": "numeric" if name == "Value" else "text"}
            for name in ("Facility", "District", "Domain", "Indicator", "Value")
        ],
        page_size=15,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "#F1F5F9", "fontWeight": 800,
            "border": f"1px solid {BORDER}", "color": TEXT,
        },
        style_cell={
            "fontFamily": "Segoe UI, sans-serif", "fontSize": "11px",
            "padding": "9px", "textAlign": "left", "border": f"1px solid {BORDER}",
            "maxWidth": "300px", "whiteSpace": "normal",
        },
        style_data_conditional=[{
            "if": {"column_id": "Value"}, "fontWeight": 800, "color": GREEN,
        }],
    )


def render_mnh_hmis_test_dashboard(
    *, start_date=None, end_date=None, scope_meta: dict | None = None,
    data_path: Path | None = None, **_,
) -> html.Div:
    """Render cached DHIS2 indicators using the active MNID scope."""
    frame = _load_sample(Path(data_path) if data_path else DEFAULT_DATA_PATH)
    if frame.empty:
        return _empty(
            "No local DHIS2 snapshot is available. Run the controlled MNH HMIS synchronization first."
        )
    filtered = _apply_scope(frame, start_date, end_date, scope_meta or {})
    if filtered.empty:
        return _empty("No DHIS2 data is available for the selected period, district, or facility.")

    period_min = filtered["period_start"].min().strftime("%b %Y")
    period_max = filtered["period_start"].max().strftime("%b %Y")
    indicator_count = filtered["indicator_id"].nunique()
    facility_count = filtered["org_unit_id"].nunique()
    district_count = filtered["district"].dropna().nunique()
    summary = _indicator_summary(filtered)

    indicator_sections = []
    available_groups = list(GROUP_ORDER) + [
        group for group in summary["indicator_group"].dropna().unique()
        if group not in GROUP_ORDER
    ]
    for group in available_groups:
        group_summary = summary[summary["indicator_group"] == group]
        if group_summary.empty:
            continue
        color = GROUP_COLORS.get(group, PURPLE)
        indicator_sections.extend([
            _section_header(
                group,
                f"{len(group_summary)} indicators · totals and latest-month movement",
                color,
            ),
            html.Div(
                [_indicator_card(row, color) for row in group_summary.itertuples(index=False)],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(205px, 1fr))",
                    "gap": "10px",
                },
            ),
        ])

    trend_cards = []
    for group in GROUP_ORDER:
        if group not in set(filtered["indicator_group"]):
            continue
        trend_cards.append(_chart_card(
            f"{group} trends",
            "Monthly totals recalculate for the active period and geographic scope.",
            _trend_figure(filtered, group, GROUP_COLORS[group]),
        ))

    district_title, district_figure = _district_figure(filtered)
    return html.Div(
        style={"background": BACKGROUND, "padding": "4px 0 28px"},
        children=[
            _hero(
                period_min, period_max, indicator_count, facility_count,
                district_count, scope_meta or {},
            ),
            _section_header(
                "Indicator portfolio",
                f"{indicator_count} indicators available in the active HMIS snapshot",
            ),
            *indicator_sections,
            _section_header(
                "Performance over time",
                "Country Profile-style monthly views by service domain",
                BLUE,
            ),
            html.Div(trend_cards, style={
                "display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(480px, 1fr))",
                "gap": "14px",
            }),
            _section_header("Geographic profile", "District comparison for priority outcomes", RED),
            _chart_card(
                "Top 15 districts",
                f"Combined {district_title.lower()} in the selected reporting window.",
                district_figure,
            ),
            _section_header(
                "Facility drill-down",
                "Use the column filters to isolate a district, facility, domain, or indicator.",
                TEAL,
            ),
            html.Div(
                _facility_table(filtered),
                style={
                    "background": SURFACE, "border": f"1px solid {BORDER}",
                    "borderRadius": "14px", "padding": "16px",
                },
            ),
        ],
    )
