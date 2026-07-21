"""Country-profile-inspired visualizations for cached DHIS2 MNH indicators."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import dash_table, dcc, html

from mnid.components.run_charts import _chart_key_slug, _trend_chart_payload

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

DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "dhis2" / "aggregates" / "hmis_test.parquet"
)

GROUP_ORDER = (
    "Births and outcomes",
    "Antenatal care",
    "Delivery and newborn care",
    "Obstetric complications and signal functions",
    "Postnatal care",
)
GROUP_COLORS = {
    "Births and outcomes": RED,
    "Antenatal care": GREEN,
    "Delivery and newborn care": BLUE,
    "Obstetric complications and signal functions": AMBER,
    "Postnatal care": TEAL,
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
INDICATOR_DESCRIPTIONS = {
    "live_births": "Live births reported by facilities in the selected scope.",
    "total_births": "Combined live births and stillbirths.",
    "fresh_stillbirths": "Fresh stillbirths reported during the selected period.",
    "macerated_stillbirths": "Macerated stillbirths reported during the selected period.",
    "maternal_deaths": "Maternal deaths reported by facilities.",
    "neonatal_deaths": "Neonatal deaths reported by facilities.",
    "stillbirths": "Combined fresh and macerated stillbirths.",
    "anc_visits": "Total recorded ANC contacts across visit stages.",
    "blood_pressure_measured": "ANC clients whose blood pressure was measured.",
    "tested_for_hiv": "ANC clients tested for HIV.",
    "screened_for_syphilis": "ANC clients screened for syphilis.",
    "at_least_4_anc_contacts": "Clients completing at least four ANC contacts.",
    "tetanus_doses_2": "ANC clients receiving two or more tetanus doses.",
    "new_anc_registrations": "New ANC registrations reported by facilities.",
    "started_anc_in_first_trimester_0_12_weeks": "Clients starting ANC within 0–12 weeks.",
    "received_120_fefo_tablets": "ANC clients receiving at least 120 FeFo tablets.",
    "received_itn_during_anc": "ANC clients receiving an insecticide-treated net.",
    "screened_for_anaemia": "ANC clients screened for anaemia.",
    "women_with_imminent_preterm_birth_receiving_acs": "Percentage of eligible women with imminent preterm birth receiving antenatal corticosteroids.",
    "uterotonic_given_after_birth": "Women receiving a uterotonic after birth.",
    "newborns_not_breathing_at_birth_receiving_bag_mask_ventilation": "Non-breathing newborns receiving bag-mask ventilation.",
    "vitamin_k_at_birth": "Newborns receiving Vitamin K at birth.",
    "facility_deliveries": "Deliveries reported through facility maternity services.",
    "delivered_at_this_facility": "Women delivering at the reporting facility.",
    "delivered_at_home_or_in_transit": "Deliveries occurring at home or in transit.",
    "delivered_by_skilled_attendant": "Deliveries attended by a skilled provider.",
    "normal_vaginal_delivery": "Normal vaginal deliveries reported by facilities.",
    "early_initiation_of_breastfeeding_within_1_hour_of_birth": "Provisional derived count of newborns breastfed within one hour; calculation requires clinical confirmation.",
    "pre_eclampsia_eclampsia_receiving_magnesium_sulphate": "Percentage of women with pre-eclampsia or eclampsia receiving magnesium sulphate.",
    "obstetric_complication_pph": "Postpartum haemorrhage complications reported by facilities.",
    "obstetric_complication_eclampsia": "Eclampsia complications reported by facilities.",
    "obstetric_complication_obstructed_labour": "Obstructed or prolonged labour complications reported by facilities.",
    "obstetric_complication_maternal_sepsis": "Maternal sepsis complications reported by facilities.",
    "signal_parenteral_antibiotics": "Facilities reporting administration of parenteral antibiotics.",
    "signal_anticonvulsants_mgso4": "Facilities reporting administration of magnesium sulphate anticonvulsants.",
    "signal_oxytocics": "Facilities reporting administration of uterotonic drugs.",
    "signal_manual_placenta_removal": "Manual removal of placenta procedures reported by facilities.",
    "signal_mva_retained_products": "Manual vacuum aspiration for retained products reported by facilities.",
    "signal_assisted_vaginal_delivery": "Assisted vaginal deliveries reported by facilities.",
    "signal_caesarean_section": "Caesarean sections reported by facilities.",
    "signal_blood_transfusion": "Blood transfusions reported by facilities.",
    "mothers_with_postnatal_complications": "Mothers with postnatal complications reported by facilities.",
    "babies_with_postnatal_complications": "Babies with postnatal complications reported by facilities.",
    "mothers_checked_within_7_days": "Mothers receiving a postnatal check within seven days.",
    "babies_checked_within_7_days": "Babies receiving a postnatal check within seven days.",
    "mothers_checked_at_6_weeks": "Mothers receiving a postnatal check at six weeks.",
    "babies_checked_at_6_weeks": "Babies receiving a postnatal check at six weeks.",
    "immediate_postpartum_family_planning": "Mothers receiving immediate postpartum family-planning services.",
    "hiv_positive_postnatal_mothers": "HIV-positive mothers recorded during postnatal care.",
    "hiv_exposed_babies_on_art_prophylaxis": "HIV-exposed babies receiving ART prophylaxis.",
    "babies_who_received_bcg": "Babies receiving BCG vaccination.",
    "babies_who_received_polio_0": "Babies receiving the Polio 0 dose.",
}
INDICATOR_COLORS = {
    "maternal_deaths": "#E11D48",
    "neonatal_deaths": "#D97706",
    "stillbirths": "#7C3AED",
    "fresh_stillbirths": "#DB2777",
    "macerated_stillbirths": "#8B5CF6",
    "total_births": "#0284C7",
    "live_births": "#16A34A",
}
SUMMARY_INDICATOR_IDS = (
    "total_births", "live_births", "stillbirths", "fresh_stillbirths",
    "macerated_stillbirths", "maternal_deaths", "neonatal_deaths",
)
TREND_INDICATOR_IDS = (
    "total_births", "live_births", "stillbirths", "maternal_deaths",
    "neonatal_deaths", "anc_visits", "facility_deliveries",
)
PERCENTAGE_INDICATOR_IDS = (
    "women_with_imminent_preterm_birth_receiving_acs",
    "pre_eclampsia_eclampsia_receiving_magnesium_sulphate",
)
DOMAIN_SNAPSHOT_IDS = {
    "Antenatal service snapshot": (
        "blood_pressure_measured", "screened_for_anaemia", "tested_for_hiv",
        "screened_for_syphilis", "at_least_4_anc_contacts", "tetanus_doses_2",
        "new_anc_registrations", "started_anc_in_first_trimester_0_12_weeks",
        "received_120_fefo_tablets", "received_itn_during_anc",
    ),
    "Delivery and newborn care snapshot": (
        "uterotonic_given_after_birth",
        "newborns_not_breathing_at_birth_receiving_bag_mask_ventilation",
        "vitamin_k_at_birth", "delivered_at_this_facility",
        "delivered_at_home_or_in_transit", "delivered_by_skilled_attendant",
        "normal_vaginal_delivery",
        "early_initiation_of_breastfeeding_within_1_hour_of_birth",
    ),
    "Obstetric complications": (
        "obstetric_complication_pph", "obstetric_complication_eclampsia",
        "obstetric_complication_obstructed_labour",
        "obstetric_complication_maternal_sepsis",
    ),
    "Emergency obstetric signal functions": (
        "signal_parenteral_antibiotics", "signal_anticonvulsants_mgso4",
        "signal_oxytocics", "signal_manual_placenta_removal",
        "signal_mva_retained_products", "signal_assisted_vaginal_delivery",
        "signal_caesarean_section", "signal_blood_transfusion",
    ),
    "Postnatal and newborn follow-up": (
        "mothers_with_postnatal_complications", "babies_with_postnatal_complications",
        "mothers_checked_within_7_days", "babies_checked_within_7_days",
        "mothers_checked_at_6_weeks", "babies_checked_at_6_weeks",
        "immediate_postpartum_family_planning", "hiv_positive_postnatal_mothers",
        "hiv_exposed_babies_on_art_prophylaxis", "babies_who_received_bcg",
        "babies_who_received_polio_0",
    ),
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
    if "value_type" not in frame.columns:
        frame["value_type"] = "count"
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
    return html.Div(
        [
            html.Div("MNH HMIS COUNTRY PROFILE", style={
                "fontSize": "10px", "fontWeight": 800, "letterSpacing": ".12em",
                "color": TEAL, "marginBottom": "10px",
            }),
            html.Div("Maternal and Neonatal Outcomes Dashboard", style={
                "fontSize": "26px", "fontWeight": 850, "color": TEXT,
                "letterSpacing": "-.04em", "lineHeight": "1.15",
            }),
            html.Div(
                "Malawi national overview · HMIS aggregate indicators · Evidence for action · Decision support",
                style={"fontSize": "12px", "color": MUTED, "marginTop": "6px"},
            ),
            html.Div([
                html.Span("Live snapshot", style={
                    "background": "#ECFDF5", "border": "1px solid #BBF7D0",
                    "color": GREEN, "fontSize": "10px", "fontWeight": 750,
                    "padding": "4px 10px", "borderRadius": "99px",
                }),
                html.Span(f"{period_min} – {period_max}", style={
                    "background": BACKGROUND, "border": f"1px solid {BORDER}",
                    "color": "#475569", "fontSize": "10px", "fontWeight": 700,
                    "padding": "4px 10px", "borderRadius": "99px",
                }),
                html.Span(f"{district_count} Districts · {facility_count} Reporting Units", style={
                    "background": BACKGROUND, "border": f"1px solid {BORDER}",
                    "color": "#475569", "fontSize": "10px", "fontWeight": 700,
                    "padding": "4px 10px", "borderRadius": "99px",
                }),
                html.Span(f"{indicator_count} Indicators", style={
                    "background": BACKGROUND, "border": f"1px solid {BORDER}",
                    "color": "#475569", "fontSize": "10px", "fontWeight": 700,
                    "padding": "4px 10px", "borderRadius": "99px",
                }),
            ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginTop": "16px"}),
        ],
        style={
            "background": SURFACE, "border": f"1px solid {BORDER}",
            "borderRadius": "16px", "padding": "22px 24px",
            "boxShadow": "0 2px 8px rgba(15,23,42,.04)", "marginBottom": "18px",
        },
    )


def _indicator_summary(frame: pd.DataFrame) -> pd.DataFrame:
    periods = sorted(frame["period_start"].dropna().unique())
    latest_period = periods[-1]
    previous_period = periods[-2] if len(periods) > 1 else None
    total = frame.groupby(
        ["indicator_id", "indicator_name", "indicator_group", "value_type"], as_index=False
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


def _summary_lookup(summary: pd.DataFrame) -> dict[str, object]:
    return {row.indicator_id: row for row in summary.itertuples(index=False)}


def _priority_alert(summary: pd.DataFrame) -> html.Div:
    lookup = _summary_lookup(summary)
    specs = [
        ("Maternal deaths", "maternal_deaths", "#E11D48"),
        ("Neonatal deaths", "neonatal_deaths", AMBER),
        ("Stillbirths", "stillbirths", PURPLE),
    ]
    present = [(label, lookup.get(indicator_id), color) for label, indicator_id, color in specs]
    present = [(label, row, color) for label, row, color in present if row is not None]
    events = int(sum(float(row.latest or 0) for _, row, _ in present))
    return html.Div(
        [
            html.Div([
                html.Div("●", style={"fontSize": "15px", "color": RED}),
                html.Div(f"{events:,}", style={"fontSize": "18px", "fontWeight": 850, "color": RED}),
                html.Div("latest-month events", style={"fontSize": "8px", "color": "#9A3412"}),
            ], style={"width": "88px", "textAlign": "center", "flexShrink": "0"}),
            html.Div(style={"width": "1px", "alignSelf": "stretch", "background": "#FED7AA"}),
            html.Div([
                html.Div("Priority Alert", style={
                    "fontSize": "12px", "fontWeight": 850, "color": "#9A3412",
                }),
                html.Div(
                    "Maternal, neonatal, or stillbirth deaths were reported in the latest month.",
                    style={"fontSize": "10px", "color": "#9A3412", "margin": "2px 0 8px"},
                ),
                html.Div([
                    html.Div([
                        html.Span(label, style={"fontSize": "10px", "fontWeight": 750, "color": "#7C2D12"}),
                        html.Span(f"{float(row.latest or 0):,.0f}", style={
                            "fontSize": "19px", "fontWeight": 850, "color": color,
                        }),
                        html.Span("Latest reporting month", style={"fontSize": "9px", "color": "#9A3412"}),
                    ], style={
                        "display": "flex", "alignItems": "baseline", "gap": "5px",
                        "background": SURFACE, "border": "1px solid #FED7AA",
                        "borderRadius": "9px", "padding": "8px 10px", "flex": "1",
                        "minWidth": "210px",
                    })
                    for label, row, color in present
                ], style={"display": "flex", "gap": "9px", "flexWrap": "wrap"}),
            ], style={"flex": "1"}),
        ],
        style={
            "display": "flex", "gap": "12px", "alignItems": "stretch",
            "background": "#FFF7ED", "border": "1px solid #FED7AA",
            "borderRadius": "11px", "padding": "10px 12px", "marginBottom": "18px",
        },
    )


def _scope_band(period_min: str, period_max: str, indicator_count: int,
                facility_count: int, district_count: int, row_count: int,
                scope_meta: dict) -> html.Div:
    items = [
        ("Period", f"{period_min} – {period_max}"),
        ("Scope", _scope_label(scope_meta, facility_count, district_count)),
        ("Districts", f"{district_count:,}"),
        ("Reporting units", f"{facility_count:,}"),
        ("Indicators", f"{indicator_count:,}"),
        ("Aggregate records", f"{row_count:,}"),
    ]
    return html.Div([
        html.Div([
            html.Span(label, style={
                "display": "block", "fontSize": "8px", "fontWeight": 800,
                "color": "#94A3B8", "textTransform": "uppercase",
                "letterSpacing": ".07em", "marginBottom": "3px",
            }),
            html.Span(value, style={"fontSize": "10px", "fontWeight": 700, "color": TEXT}),
        ], style={"padding": "9px 13px", "borderRight": f"1px solid {BORDER}"})
        for label, value in items
    ], style={
        "display": "flex", "flexWrap": "wrap", "background": BACKGROUND,
        "border": f"1px solid {BORDER}", "borderRadius": "10px",
        "overflow": "hidden", "marginBottom": "18px",
    })


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
            html.Div(f"{float(row.latest or 0):,.0f}", style={
                "fontSize": "25px", "fontWeight": 850, "color": color,
                "letterSpacing": "-.03em", "marginTop": "8px",
            }),
            html.Div("Latest reporting month", style={
                "fontSize": "9px", "color": MUTED, "marginTop": "-2px",
            }),
            html.Div([
                html.Span(change_label, style={
                    "fontSize": "9px", "fontWeight": 750, "color": change_color,
                    "background": change_bg, "borderRadius": "99px", "padding": "3px 7px",
                }),
                html.Span(f"Total {float(row.total):,.0f}", style={
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
    figure_height = getattr(getattr(figure, "layout", None), "height", None) or 370
    return html.Div(
        [
            html.Div(title, style={"fontSize": "14px", "fontWeight": 800, "color": TEXT}),
            html.Div(subtitle, style={"fontSize": "10px", "color": MUTED, "marginTop": "3px"}),
            dcc.Graph(
                figure=figure,
                config={"displayModeBar": False, "responsive": True},
                style={"height": f"{figure_height}px"},
            ),
        ],
        style={
            "background": SURFACE, "border": f"1px solid {BORDER}",
            "borderRadius": "14px", "padding": "16px",
            "boxShadow": "0 2px 10px rgba(15,23,42,.04)",
        },
    )


def _indicator_chart_card(frame: pd.DataFrame, row, color: str):
    series = (
        frame[frame["indicator_id"] == row.indicator_id]
        .groupby("period_start", as_index=False)["value"].sum()
        .sort_values("period_start")
        .rename(columns={"period_start": "month"})
    )
    chart_key = f"hmis-{_chart_key_slug(row.indicator_id)}"
    return _trend_chart_payload(
        chart_key=chart_key,
        title=row.indicator_name,
        subtitle=INDICATOR_DESCRIPTIONS.get(
            row.indicator_id, "Facility-reported HMIS aggregate over time."
        ),
        accent=color,
        y_title="Percentage (%)" if row.value_type == "percentage" else "Reported count",
        series_df=series[["month", "value"]],
        multi=False,
    )["card"]


def _latest_indicator_totals(frame: pd.DataFrame, indicator_ids: tuple[str, ...]) -> pd.DataFrame:
    selected = frame[frame["indicator_id"].isin(indicator_ids)].copy()
    if selected.empty:
        return pd.DataFrame(columns=["indicator_id", "indicator_name", "value"])
    latest_period = selected["period_start"].max()
    return (
        selected[selected["period_start"] == latest_period]
        .groupby(["indicator_id", "indicator_name"], as_index=False)["value"].sum()
        .sort_values("value")
    )


def _indicator_comparison_figure(
    frame: pd.DataFrame, indicator_ids: tuple[str, ...], color: str,
) -> go.Figure:
    values = _latest_indicator_totals(frame, indicator_ids)
    figure = go.Figure()
    if values.empty:
        return figure
    figure.add_trace(go.Bar(
        x=values["value"], y=values["indicator_name"], orientation="h",
        marker={"color": color, "opacity": .82, "line": {"color": color, "width": .5}},
        text=values["value"].map(lambda value: f"{value:,.0f}"),
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,.0f}<extra></extra>",
    ))
    height = max(340, 54 * len(values) + 90)
    figure.update_layout(
        height=height, margin={"l": 260, "r": 70, "t": 18, "b": 38},
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE, showlegend=False,
        font={"color": TEXT, "size": 10},
        xaxis={"title": "Reported count · latest month", "gridcolor": "#EEF2F7", "zeroline": False},
        yaxis={"title": None, "showgrid": False, "automargin": True},
    )
    return figure


def _outcome_composition_figure(frame: pd.DataFrame) -> go.Figure:
    values = _latest_indicator_totals(
        frame, ("live_births", "fresh_stillbirths", "macerated_stillbirths")
    )
    color_by_id = {
        "live_births": "#16A34A", "fresh_stillbirths": "#DB2777",
        "macerated_stillbirths": "#8B5CF6",
    }
    figure = go.Figure()
    if values.empty:
        return figure
    figure.add_trace(go.Pie(
        labels=values["indicator_name"], values=values["value"], hole=.64,
        marker={"colors": [color_by_id.get(value, BLUE) for value in values["indicator_id"]]},
        textinfo="percent", hovertemplate="<b>%{label}</b><br>%{value:,.0f} (%{percent})<extra></extra>",
    ))
    figure.update_layout(
        height=390, margin={"l": 12, "r": 12, "t": 16, "b": 45},
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        legend={"orientation": "h", "y": -.08, "x": .5, "xanchor": "center"},
        font={"color": TEXT, "size": 10},
        annotations=[{"text": "Birth<br>outcomes", "x": .5, "y": .5, "showarrow": False,
                      "font": {"size": 14, "color": TEXT}}],
    )
    return figure


def _percentage_status_card(frame: pd.DataFrame, indicator_id: str, color: str) -> html.Div:
    selected = frame[frame["indicator_id"] == indicator_id].copy()
    if selected.empty:
        return html.Div()
    latest = selected[selected["period_start"] == selected["period_start"].max()]
    median = float(latest["value"].median()) if not latest.empty else 0.0
    reporting_units = int(latest["org_unit_id"].nunique())
    above_100 = int((latest["value"] > 100).sum())
    name = str(latest["indicator_name"].iloc[0])
    bounded = max(0.0, min(median, 100.0))
    return html.Div([
        html.Div(name, style={
            "fontSize": "12px", "fontWeight": 800, "color": TEXT,
            "lineHeight": "1.4", "minHeight": "35px",
        }),
        html.Div([
            html.Div(style={
                "width": "92px", "height": "92px", "borderRadius": "50%",
                "background": f"conic-gradient({color} {bounded:.1f}%, #E2E8F0 0)",
                "display": "flex", "alignItems": "center", "justifyContent": "center",
            }, children=html.Div(f"{median:,.1f}%", style={
                "width": "68px", "height": "68px", "borderRadius": "50%",
                "background": SURFACE, "display": "flex", "alignItems": "center",
                "justifyContent": "center", "fontSize": "16px", "fontWeight": 850,
                "color": color,
            })),
            html.Div([
                html.Div("Median facility percentage", style={"fontSize": "10px", "color": MUTED}),
                html.Div(f"{reporting_units:,} reporting units", style={
                    "fontSize": "11px", "fontWeight": 750, "color": TEXT, "marginTop": "6px",
                }),
                html.Div(
                    f"{above_100:,} values above 100%" if above_100 else "No values above 100%",
                    style={
                        "fontSize": "10px", "fontWeight": 700, "marginTop": "6px",
                        "color": RED if above_100 else GREEN,
                    },
                ),
            ], style={"flex": "1"}),
        ], style={"display": "flex", "gap": "16px", "alignItems": "center", "marginTop": "14px"}),
        html.Div(style={
            "height": "6px", "borderRadius": "4px", "background": "#E2E8F0",
            "overflow": "hidden", "marginTop": "16px",
        }, children=html.Div(style={
            "height": "100%", "width": f"{bounded:.1f}%", "background": color,
        })),
    ], style={
        "background": SURFACE, "border": f"1px solid {BORDER}",
        "borderTop": f"3px solid {color}", "borderRadius": "12px", "padding": "16px",
        "boxShadow": "0 2px 8px rgba(15,23,42,.04)",
    })


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

    summary_lookup = _summary_lookup(summary)
    summary_cards = [
        _indicator_card(
            summary_lookup[indicator_id],
            INDICATOR_COLORS.get(indicator_id, GROUP_COLORS["Births and outcomes"]),
        )
        for indicator_id in SUMMARY_INDICATOR_IDS
        if indicator_id in summary_lookup
    ]

    trend_cards = [
        _indicator_chart_card(
            filtered, summary_lookup[indicator_id],
            INDICATOR_COLORS.get(
                indicator_id,
                GROUP_COLORS.get(summary_lookup[indicator_id].indicator_group, BLUE),
            ),
        )
        for indicator_id in TREND_INDICATOR_IDS
        if indicator_id in summary_lookup
    ]
    percentage_cards = [
        _percentage_status_card(
            filtered, indicator_id,
            GREEN if indicator_id.startswith("women_") else AMBER,
        )
        for indicator_id in PERCENTAGE_INDICATOR_IDS
        if indicator_id in summary_lookup
    ]
    snapshot_colors = (GREEN, BLUE, RED, AMBER, TEAL)
    snapshot_cards = [
        _chart_card(
            title,
            "Latest reporting month · active geographic scope",
            _indicator_comparison_figure(filtered, indicator_ids, snapshot_colors[index]),
        )
        for index, (title, indicator_ids) in enumerate(DOMAIN_SNAPSHOT_IDS.items())
    ]

    district_title, district_figure = _district_figure(filtered)
    return html.Div(
        style={"background": BACKGROUND, "padding": "4px 0 28px"},
        children=[
            _hero(
                period_min, period_max, indicator_count, facility_count,
                district_count, scope_meta or {},
            ),
            _priority_alert(summary),
            _scope_band(
                period_min, period_max, indicator_count, facility_count,
                district_count, len(filtered), scope_meta or {},
            ),
            _section_header(
                "Country summary · Latest reporting month",
                "Key birth and mortality indicators; totals reflect the active filter window",
            ),
            html.Div(summary_cards, style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fit, minmax(190px, 1fr))",
                "gap": "12px", "marginBottom": "18px",
            }),
            _section_header(
                "Priority trends",
                "Run charts are reserved for indicators where change over time supports action",
                BLUE,
            ),
            html.Div(trend_cards, style={
                "display": "grid", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
                "gap": "14px", "marginBottom": "18px",
            }),
            _section_header(
                "Birth outcome composition",
                "Latest-month balance of live births, fresh stillbirths, and macerated stillbirths",
                PURPLE,
            ),
            html.Div([
                _chart_card(
                    "Birth outcome mix", "Latest reporting month · share of recorded outcomes",
                    _outcome_composition_figure(filtered),
                ),
                _chart_card(
                    "Priority outcomes by district",
                    f"Top districts by combined {district_title.lower()} in the selected window",
                    district_figure,
                ),
            ], style={
                "display": "grid", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
                "gap": "14px", "marginBottom": "18px",
            }),
            _section_header(
                "Clinical service snapshots",
                "Related indicators are compared together instead of repeating identical chart forms",
                GREEN,
            ),
            html.Div(snapshot_cards, style={
                "display": "grid", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
                "gap": "14px", "marginBottom": "18px",
            }),
            _section_header(
                "Coverage and treatment status",
                "Median facility percentages for the latest month; out-of-range values remain visible",
                AMBER,
            ),
            html.Div(percentage_cards, style={
                "display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(300px, 1fr))",
                "gap": "14px", "marginBottom": "18px",
            }),
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
