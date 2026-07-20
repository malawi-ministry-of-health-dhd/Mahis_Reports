"""Read-only sample visualizations for five verified DHIS2 indicators."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
from dash import dash_table, dcc, html

GREEN, BLUE, AMBER, RED, PURPLE = "#15803D", "#2563EB", "#D97706", "#DC2626", "#7C3AED"
TEXT, MUTED, BORDER = "#0F172A", "#64748B", "#E2E8F0"
PALETTE = [GREEN, BLUE, AMBER, RED, PURPLE]
DEFAULT_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "dhis2" / "aggregates" / "hmis_test.parquet"


def _empty(message: str) -> html.Div:
    return html.Div(message, style={"padding": "28px", "background": "#FFF", "border": f"1px solid {BORDER}", "borderRadius": "14px", "color": MUTED})


def _load_sample(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()
    frame["period_start"] = pd.to_datetime(frame.get("period_start"), errors="coerce")
    frame["value"] = pd.to_numeric(frame.get("value"), errors="coerce")
    return frame


def _apply_scope(frame: pd.DataFrame, start_date, end_date, scope_meta: dict) -> pd.DataFrame:
    result = frame.copy()
    start, end = pd.to_datetime(start_date, errors="coerce"), pd.to_datetime(end_date, errors="coerce")
    if not pd.isna(start): result = result[result["period_start"] >= start]
    if not pd.isna(end): result = result[result["period_start"] <= end]
    districts = {str(item) for item in scope_meta.get("selected_districts") or []}
    facilities = {str(item) for item in scope_meta.get("selected_facilities") or []}
    if facilities:
        result = result[result["org_unit_name"].astype(str).isin(facilities) | result["facility_code"].astype(str).isin(facilities) | result["org_unit_id"].astype(str).isin(facilities)]
    elif districts:
        result = result[result["district"].astype(str).isin(districts)]
    return result


def _card(label: str, value: float, color: str) -> html.Div:
    return html.Div(style={"background": "#FFF", "border": f"1px solid {BORDER}", "borderTop": f"4px solid {color}", "borderRadius": "12px", "padding": "15px"}, children=[
        html.Div(label, style={"fontSize": "12px", "fontWeight": 700, "color": MUTED, "minHeight": "34px"}),
        html.Div(f"{value:,.0f}", style={"fontSize": "25px", "fontWeight": 800, "color": TEXT, "marginTop": "6px"}),
    ])


def _chart_card(title: str, subtitle: str, figure) -> html.Div:
    return html.Div(style={"background": "#FFF", "border": f"1px solid {BORDER}", "borderRadius": "14px", "padding": "16px"}, children=[
        html.Div(title, style={"fontSize": "15px", "fontWeight": 800, "color": TEXT}),
        html.Div(subtitle, style={"fontSize": "11px", "color": MUTED, "marginTop": "3px"}),
        dcc.Graph(figure=figure, config={"displayModeBar": False}, style={"height": "350px"}),
    ])


def render_mnh_hmis_test_dashboard(*, start_date=None, end_date=None, scope_meta: dict | None = None, data_path: Path | None = None, **_) -> html.Div:
    """Render five locally cached DHIS2 indicators with existing MNID scope filters."""
    frame = _load_sample(Path(data_path) if data_path else DEFAULT_DATA_PATH)
    if frame.empty:
        return _empty("No local DHIS2 sample is available. Run the controlled MNH HMIS sample synchronization first.")
    filtered = _apply_scope(frame, start_date, end_date, scope_meta or {})
    if filtered.empty:
        return _empty("No DHIS2 sample data is available for the selected period, district, or facility.")

    totals = filtered.groupby(["indicator_id", "indicator_name"], as_index=False)["value"].sum().sort_values("indicator_name")
    cards = [_card(row.indicator_name, row.value, PALETTE[index % 5]) for index, row in enumerate(totals.itertuples(index=False))]
    trend = filtered.groupby(["period_start", "indicator_name"], as_index=False)["value"].sum()
    trend_fig = px.line(trend, x="period_start", y="value", color="indicator_name", markers=True, color_discrete_sequence=PALETTE, labels={"period_start": "Month", "value": "Reported value", "indicator_name": "Indicator"})
    trend_fig.update_layout(margin={"l": 35, "r": 15, "t": 20, "b": 35}, legend={"orientation": "h", "y": -0.25}, plot_bgcolor="#FFF", paper_bgcolor="#FFF")
    district = filtered.dropna(subset=["district"]).groupby("district", as_index=False)["value"].sum().nlargest(15, "value").sort_values("value")
    district_fig = px.bar(district, x="value", y="district", orientation="h", color_discrete_sequence=[GREEN], labels={"value": "Combined reported value", "district": "District"})
    district_fig.update_layout(margin={"l": 25, "r": 15, "t": 20, "b": 35}, plot_bgcolor="#FFF", paper_bgcolor="#FFF")
    facility = filtered.groupby(["org_unit_name", "district", "indicator_name"], dropna=False, as_index=False)["value"].sum().sort_values("value", ascending=False).head(100)
    facility = facility.rename(columns={"org_unit_name": "Facility", "district": "District", "indicator_name": "Indicator", "value": "Value"})
    table = dash_table.DataTable(data=facility.to_dict("records"), columns=[{"name": name, "id": name, "type": "numeric" if name == "Value" else "text"} for name in ("Facility", "District", "Indicator", "Value")], page_size=15, sort_action="native", filter_action="native", style_table={"overflowX": "auto"}, style_header={"backgroundColor": "#F8FAFC", "fontWeight": 800, "border": f"1px solid {BORDER}"}, style_cell={"fontFamily": "Segoe UI, sans-serif", "fontSize": "12px", "padding": "9px", "textAlign": "left", "border": f"1px solid {BORDER}"})
    period_min, period_max = filtered["period_start"].min().strftime("%b %Y"), filtered["period_start"].max().strftime("%b %Y")
    return html.Div(style={"background": "#F8FAFC", "padding": "4px 0 28px"}, children=[
        html.Div([html.Div("MNH HMIS test", style={"fontSize": "24px", "fontWeight": 850, "color": TEXT}), html.Div(f"Sample aggregate data from Malawi HMIS DHIS2 · {period_min}–{period_max} · {filtered['org_unit_id'].nunique():,} facilities", style={"fontSize": "12px", "color": MUTED, "marginTop": "4px"})], style={"marginBottom": "16px"}),
        html.Div(cards, style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(190px, 1fr))", "gap": "10px", "marginBottom": "14px"}),
        html.Div([_chart_card("Monthly indicator trends", "Totals recalculate for the active MNID scope.", trend_fig), _chart_card("Top 15 districts", "Combined volume across the five sample indicators.", district_fig)], style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(420px, 1fr))", "gap": "12px", "marginBottom": "14px"}),
        html.Div([html.Div("Facility detail", style={"fontSize": "15px", "fontWeight": 800, "color": TEXT, "marginBottom": "10px"}), table], style={"background": "#FFF", "border": f"1px solid {BORDER}", "borderRadius": "14px", "padding": "16px"}),
    ])
