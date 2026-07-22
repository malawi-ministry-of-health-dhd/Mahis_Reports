"""Operational Readiness tab - EmONC-style facility readiness assessment.

Rebuilt against "Dashboard readiness v2.docx": 5 lazily-loaded sub-tabs
(Overview / Signal Functions / People / Products & Commodities / Systems &
Infrastructure). Each tab shows a single-facility detail view when exactly one
facility is in scope, or a comparison table across facilities otherwise -
matching the doc's section 9 interaction rules.

Signal Functions is the one section with real underlying data: the 9 WHO
EmONC signal functions already exist as ordinary MNID coverage indicators
(mnid/core/indicators.py, sub_category='signal_functions') - a facility's
status here is a re-interpretation of the same aggregate numerator/denominator
data every other MNID view already reads, not new computation infrastructure.
People / Products & Commodities / Systems & Infrastructure have no real MAHIS
data yet, so their rows are built the same way Nest360's not-yet-available
indicators are (mnid/dashboards/MNH-Nest360/indicators.py): present, properly
labeled "Not reported", ready to light up once real data exists - no
fabricated values.
"""
from __future__ import annotations

import pandas as pd
from dash import html, dcc, callback, dash_table, Input, Output, State
from dash.exceptions import PreventUpdate

from mnid.charts.chart_helpers import _cov, _grouped_filter_counts
from mnid.core.constants import FACILITY_NAMES, FACILITY_DISTRICT
from mnid.core.data_utils import resolve_facility_level, _remember_ui_payload, _restore_ui_dataframe
from mnid.aggregation.store import get_aggregate as _get_aggregate

GREEN = "#15803D"
AMBER = "#D97706"
RED = "#DC2626"
MUTED = "#64748B"
BORDER = "#E2E8F0"
SURFACE = "#FFFFFF"
BACKGROUND = "#F8FAFC"
TEXT = "#0F172A"

STATUS_COLORS = {
    "green": (GREEN, "#DCFCE7"),
    "amber": (AMBER, "#FEF3C7"),
    "red": (RED, "#FEE2E2"),
    "na": (MUTED, "#F1F5F9"),
    "awaiting": (MUTED, "#F1F5F9"),
}
STATUS_LABELS = {
    "green": "Green", "amber": "Amber", "red": "Red",
    "na": "N/A", "awaiting": "Not reported",
}

# ---------------------------------------------------------------------------
# The 9 WHO EmONC signal functions, already tracked as ordinary MNID coverage
# indicators (mnid/core/indicators.py:751-849, category='Labour',
# sub_category='signal_functions'). `comprehensive_only` marks the 2 that a
# Primary-level facility is not expected to perform (Table 4's N/A examples).
# ---------------------------------------------------------------------------
SIGNAL_FUNCTIONS = [
    {"id": "mnid_lab_moh_028", "label": "Parenteral antibiotics", "comprehensive_only": False},
    {"id": "mnid_lab_moh_029", "label": "Anticonvulsants (magnesium sulphate)", "comprehensive_only": False},
    {"id": "mnid_lab_moh_030", "label": "Uterotonics (oxytocics)", "comprehensive_only": False},
    {"id": "mnid_lab_moh_031", "label": "Manual removal of placenta", "comprehensive_only": False},
    {"id": "mnid_lab_moh_032", "label": "Removal of retained products (MVA)", "comprehensive_only": False},
    {"id": "mnid_lab_moh_033", "label": "Assisted vaginal delivery", "comprehensive_only": False},
    {"id": "mnid_lab_moh_034", "label": "Newborn resuscitation (bag and mask)", "comprehensive_only": False},
    {"id": "mnid_lab_moh_035", "label": "Caesarean section", "comprehensive_only": True},
    {"id": "mnid_lab_moh_036", "label": "Blood transfusion", "comprehensive_only": True},
]

# No per-client "performed" flag exists yet for these (doc Table 5) - shown as
# awaiting data, same convention as People/Products/Systems below.
NEWBORN_SIGNAL_FUNCTIONS = [
    "Initiate and support early and exclusive breastfeeding",
    "Resuscitate a newborn using a bag and mask",
    "Administer parenteral antibiotics to newborns",
    "Provide immediate Kangaroo Mother Care for preterm or low-birthweight newborns",
    "Provide thermal care using a radiant warmer or incubator",
    "Administer oxygen therapy with pulse oximetry",
    "Provide CPAP treatment",
    "Provide phototherapy",
    "Provide newborn blood transfusion",
    "Enable assisted feeding with expressed breast milk (cup, spoon or tube)",
    "Administer intravenous fluids",
    "Provide invasive mechanical ventilation",
    "Screen and treat retinopathy of prematurity",
]

CADRES_NEONATAL = ["Nurses/midwives", "Clinical officers", "General doctors",
                    "Paediatricians/neonatologists", "Data clerks"]
CADRES_MATERNITY = ["Anesthesiologists", "Anaesthetist technicians", "Clinical officers",
                     "General medical doctors", "Nurse-midwives/obstetric nurses",
                     "Nurse-midwife technicians", "Obstetrician-gynaecologists"]

TRACER_MEDICINES_MATERNITY = [
    ("Anemia prevention", "Iron supplementation"),
    ("Maternal nutrition", "Multiple micronutrient supplementation"),
    ("Postpartum hemorrhage", "Oxytocin injection"),
    ("Postpartum hemorrhage", "Misoprostol 200 microgram tablets"),
    ("Postpartum hemorrhage", "Tranexamic acid"),
    ("Pre-eclampsia/eclampsia", "Magnesium sulphate injection"),
    ("Pre-eclampsia/eclampsia", "Calcium gluconate injection"),
    ("Pre-eclampsia/eclampsia", "Hydralazine injection"),
    ("Maternal sepsis", "Injectable broad-spectrum antibiotic"),
    ("Preterm labour management", "Dexamethasone injection"),
    ("Fluid replacement", "Sodium chloride 0.9% IV solution"),
    ("Fluid replacement", "Ringer's lactate IV solution"),
]
TRACER_MEDICINES_NEWBORN = [
    ("Fluids and glucose management", "Dextrose 10%"),
    ("Fluid replacement", "Sodium chloride 0.9%"),
    ("Neonatal sepsis", "Gentamicin injection"),
    ("Neonatal sepsis", "Benzylpenicillin injection"),
    ("Neonatal sepsis", "Ampicillin injection"),
    ("Management of seizures", "Phenobarbitone injection"),
    ("Apnoea of prematurity", "Caffeine citrate"),
    ("Prevention of vitamin K deficiency bleeding", "Vitamin K1 injection"),
    ("Advanced neonatal resuscitation", "Adrenaline/epinephrine injection"),
    ("Emergency electrolyte management", "Calcium gluconate 10% injection"),
]
EQUIPMENT_MATERNITY = [
    ("Delivery care", "Delivery packs"),
    ("Postpartum hemorrhage", "Calibrated blood-loss measurement drapes"),
    ("Maternal sepsis", "FAST-M Charts"),
    ("Maternal monitoring", "Partograph"),
    ("Maternal monitoring", "Fetal stethoscopes/Pinards"),
    ("Maternal monitoring", "Fetal monitors/Dopplers"),
    ("Antenatal diagnostics", "Ultrasound scans"),
    ("Antenatal diagnostics", "Blood-pressure machine"),
    ("Newborn resuscitation", "Resuscitation table with heat source"),
    ("Newborn resuscitation", "Bag and mask, size 0"),
    ("Newborn resuscitation", "Bag and mask, size 1"),
]
EQUIPMENT_NEWBORN = [
    ("Glucose monitoring", "Glucometer"),
    ("Resuscitation", "Neonatal bag and masks, sizes 0 and 1"),
    ("Oxygen therapy", "Pulse oximeter"),
    ("Oxygen therapy", "Oxygen concentrator"),
    ("Oxygen therapy", "Oxygen cylinder"),
    ("Thermal care", "Incubator"),
    ("Thermal care", "Radiant warmer with probes"),
    ("Kangaroo Mother Care", "Designated KMC beds or spaces"),
    ("Jaundice care", "Phototherapy unit"),
    ("Jaundice care", "Bilirubinometer"),
    ("Respiratory support", "CPAP unit"),
]
INFRASTRUCTURE_MATERNITY = [
    ("Capacity", "Number of combined labour and delivery beds"),
    ("Physical environment", "Adequate lighting is available during the day and night"),
    ("Physical environment", "Adequate ventilation"),
    ("Surgical capacity", "Functional major operating theatre"),
    ("Surgical capacity", "Maternity theatre supported by backup power"),
    ("Respectful care infrastructure", "Labour companion permitted during delivery"),
    ("WASH and waste management", "Reliable running water available in maternity"),
    ("WASH and waste management", "Functional and private toilets available near maternity"),
    ("WASH and waste management", "Sharps container available"),
    ("WASH and waste management", "Functional autoclave available"),
]
INFRASTRUCTURE_NEONATAL = [
    ("Capacity", "Number of neonatal cots"),
    ("Capacity", "Total neonatal unit capacity (cots, warmers, incubators)"),
    ("Capacity", "Neonatal unit occupancy"),
    ("Capacity", "Number of KMC beds"),
    ("Spatial organisation", "Designated area for high-risk or acutely ill newborns"),
    ("Spatial organisation", "Isolation area for inborn newborns"),
    ("Power supply", "Stable electricity supply during the previous seven days"),
    ("Oxygen infrastructure", "Functional oxygen source available in the neonatal unit"),
    ("Family-centred care", "Mothers and caregivers allowed to visit at any time"),
    ("WASH and waste management", "Reliable running water available in the neonatal unit"),
]
REFERRAL_TRANSPORT = [
    "Dedicated neonatal transport cot/trolley with thermal protection and portable oxygen",
    "Functional motorised vehicle ambulances",
    "Sufficient fuel available to transport referrals",
    "Driver available",
    "Nurse or paramedic available to transport newborns today",
    "Routine preventive maintenance schedule available",
    "Person responsible for corrective maintenance of motor vehicles",
    "Fuel-management plan available",
]
DATA_QI_SYSTEMS = [
    "Maternity register available",
    "Newborn register available",
    "Electronic medical record for maternity",
    "Facility quality-improvement dashboard",
    "Maternity ward QI team available",
    "Neonatal care QI team available",
]


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

def _status_badge(status: str) -> html.Span:
    color, bg = STATUS_COLORS.get(status, (MUTED, "#F1F5F9"))
    return html.Span(STATUS_LABELS.get(status, status), style={
        "fontSize": "10px", "fontWeight": "700", "padding": "2px 9px",
        "borderRadius": "99px", "background": bg, "color": color,
    })


def _data_table(columns: list[str], rows: list[list]) -> dash_table.DataTable:
    return dash_table.DataTable(
        data=[dict(zip(columns, row)) for row in rows],
        columns=[{"name": c, "id": c} for c in columns],
        page_size=15,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "#F1F5F9", "fontWeight": 800,
            "border": f"1px solid {BORDER}", "color": TEXT, "fontSize": "11px",
        },
        style_cell={
            "fontFamily": "Segoe UI, sans-serif", "fontSize": "11px",
            "padding": "9px", "textAlign": "left", "border": f"1px solid {BORDER}",
            "maxWidth": "320px", "whiteSpace": "normal",
        },
    )


def _card(children, **style) -> html.Div:
    base = {
        "background": SURFACE, "border": f"1px solid {BORDER}", "borderRadius": "14px",
        "padding": "16px", "boxShadow": "0 2px 8px rgba(15,23,42,.04)", "marginBottom": "16px",
    }
    base.update(style)
    return html.Div(children, style=base)


def _section_title(text: str) -> html.Div:
    return html.Div(text, style={
        "fontSize": "13px", "fontWeight": 800, "color": TEXT, "marginBottom": "10px",
    })


def _summary_stat(label: str, value) -> html.Div:
    return html.Div([
        html.Div(str(value), style={"fontSize": "24px", "fontWeight": 850, "color": TEXT, "letterSpacing": "-.02em"}),
        html.Div(label, style={"fontSize": "10px", "color": MUTED, "marginTop": "2px"}),
    ], style={
        "background": BACKGROUND, "border": f"1px solid {BORDER}", "borderRadius": "10px",
        "padding": "12px 14px", "flex": "1", "minWidth": "140px",
    })


def _facility_universe(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty or "Facility_CODE" not in df.columns:
        return []
    return sorted(df["Facility_CODE"].dropna().astype(str).unique().tolist())


def _facility_label(code: str) -> str:
    return FACILITY_NAMES.get(code, code)


def _facility_district(code: str) -> str:
    return FACILITY_DISTRICT.get(code, "")


def _numerators_by_facility(indicator_id: str, numerator_filters: dict,
                             df: pd.DataFrame, agg_df: pd.DataFrame | None,
                             start_date, end_date) -> dict[str, int]:
    """{facility_code: numerator_count} for one indicator over the window.

    Prefers the pre-built aggregate (single filtered groupby, same fast path
    every other MNID view uses); falls back to a live groupby over raw rows
    when the aggregate isn't available - same resilience pattern used
    throughout mnid/views/trends.py.
    """
    if agg_df is not None and not agg_df.empty:
        from mnid.aggregation.store import resolve_indicator_id as _resolve_id, _candidate_grains, _floor_to_period
        resolved = _resolve_id(agg_df, indicator_id)
        grains = _candidate_grains("monthly")
        try:
            start_ts = pd.to_datetime(start_date) if start_date else agg_df["period_start"].min()
            end_ts = pd.to_datetime(end_date) if end_date else agg_df["period_start"].max()
            floor = min(_floor_to_period(start_ts, g) for g in grains)
            mask = (
                (agg_df["indicator_id"] == resolved)
                & (agg_df["grain"].isin(grains))
                & (agg_df["period_start"] >= floor)
                & (agg_df["period_start"] <= end_ts)
            )
            sub = agg_df[mask]
            if not sub.empty:
                return sub.groupby("facility_code")["numerator"].sum().astype(int).to_dict()
        except Exception:
            pass
    if df is None or df.empty or "Facility_CODE" not in df.columns:
        return {}
    counts = _grouped_filter_counts(df, ["Facility_CODE"], numerator_filters)
    return {str(k): int(v) for k, v in counts.items()}


def _scope_view(facility_codes: list[str], detail_fn, comparison_fn):
    """Single facility in scope -> detail view; otherwise -> comparison view."""
    if len(facility_codes) == 1:
        return detail_fn(facility_codes[0])
    return comparison_fn(facility_codes)


# ---------------------------------------------------------------------------
# Signal Functions
# ---------------------------------------------------------------------------

def _signal_function_rows(facility_codes: list[str], df: pd.DataFrame,
                           agg_df: pd.DataFrame | None, start_date, end_date) -> dict:
    """{sig_id: {facility_code: numerator}} for all 9 signal functions."""
    return {
        sf["id"]: _numerators_by_facility(sf["id"], {}, df, agg_df, start_date, end_date)
        for sf in SIGNAL_FUNCTIONS
    }


def _facility_status(sf: dict, numerators: dict, code: str, level: str) -> str:
    if sf["comprehensive_only"] and level == "Primary":
        return "na"
    return "green" if numerators.get(code, 0) > 0 else "red"


def _classify_emonc(numerators_by_sig: dict, code: str, level: str) -> str:
    statuses = {sf["id"]: _facility_status(sf, numerators_by_sig[sf["id"]], code, level) for sf in SIGNAL_FUNCTIONS}
    basic = [sf for sf in SIGNAL_FUNCTIONS if not sf["comprehensive_only"]]
    comprehensive = [sf for sf in SIGNAL_FUNCTIONS if sf["comprehensive_only"]]
    basic_ok = all(statuses[sf["id"]] == "green" for sf in basic)
    comp_ok = comprehensive and all(statuses[sf["id"]] == "green" for sf in comprehensive)
    if basic_ok and comp_ok:
        return "CEmONC"
    if basic_ok:
        return "BEmONC"
    return "Unclassified"


def _signal_functions_detail(code: str, numerators_by_sig: dict, df: pd.DataFrame) -> html.Div:
    level = resolve_facility_level(code, _facility_label(code))
    rows = []
    for sf in SIGNAL_FUNCTIONS:
        status = _facility_status(sf, numerators_by_sig[sf["id"]], code, level)
        rows.append(html.Div([
            html.Span(sf["label"], style={"fontSize": "12px", "color": TEXT, "flex": "1"}),
            _status_badge(status),
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "padding": "8px 0", "borderBottom": f"1px solid {BORDER}"}))
    classification = _classify_emonc(numerators_by_sig, code, level)
    return html.Div([
        _card([
            html.Div([
                html.Div(_facility_label(code), style={"fontSize": "15px", "fontWeight": 800, "color": TEXT}),
                html.Div(f"{_facility_district(code)} · {level} · {classification}", style={"fontSize": "11px", "color": MUTED, "marginTop": "2px"}),
            ], style={"marginBottom": "12px"}),
            _section_title("Maternal Signal Functions"),
            html.Div(rows),
        ]),
        _card([
            _section_title("Newborn Signal Functions"),
            html.Div([
                html.Div([
                    html.Span(label, style={"fontSize": "12px", "color": TEXT, "flex": "1"}),
                    _status_badge("awaiting"),
                ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "padding": "8px 0", "borderBottom": f"1px solid {BORDER}"})
                for label in NEWBORN_SIGNAL_FUNCTIONS
            ]),
        ]),
    ])


def _signal_functions_comparison(facility_codes: list[str], numerators_by_sig: dict) -> html.Div:
    rows = []
    for sf in SIGNAL_FUNCTIONS:
        eligible = [
            code for code in facility_codes
            if not (sf["comprehensive_only"] and resolve_facility_level(code, _facility_label(code)) == "Primary")
        ]
        performing = [code for code in eligible if numerators_by_sig[sf["id"]].get(code, 0) > 0]
        n_eligible = len(eligible)
        n_performing = len(performing)
        pct = round(n_performing / n_eligible * 100, 1) if n_eligible else 0.0
        status = "na" if n_eligible == 0 else ("green" if pct >= 80 else "amber" if pct >= 50 else "red")
        rows.append([
            sf["label"], n_eligible,
            f"{n_performing} ({pct:.0f}%)" if n_eligible else "N/A",
            f"{n_eligible - n_performing} ({100 - pct:.0f}%)" if n_eligible else "N/A",
            STATUS_LABELS[status],
        ])
    return _card([
        _section_title(f"Signal-Function Performance · {len(facility_codes)} facilities in scope"),
        _data_table(["Signal function", "Eligible facilities", "Performing, n (%)", "Not performing, n (%)", "Status"], rows),
        html.Div(
            "Green: ≥80% of eligible facilities perform the function. Amber: 50-79%. Red: <50%. "
            "Only facilities expected to perform the function (by facility level) count toward eligibility.",
            style={"fontSize": "10px", "color": MUTED, "marginTop": "8px"},
        ),
    ])


def _build_signal_functions_tab(facility_codes: list[str], df: pd.DataFrame,
                                 agg_df: pd.DataFrame | None, start_date, end_date) -> html.Div:
    numerators_by_sig = _signal_function_rows(facility_codes, df, agg_df, start_date, end_date)
    return _scope_view(
        facility_codes,
        detail_fn=lambda code: _signal_functions_detail(code, numerators_by_sig, df),
        comparison_fn=lambda codes: _signal_functions_comparison(codes, numerators_by_sig),
    )


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def _build_overview_tab(facility_codes: list[str], df: pd.DataFrame,
                         agg_df: pd.DataFrame | None, start_date, end_date) -> html.Div:
    numerators_by_sig = _signal_function_rows(facility_codes, df, agg_df, start_date, end_date)
    classifications = {
        code: _classify_emonc(numerators_by_sig, code, resolve_facility_level(code, _facility_label(code)))
        for code in facility_codes
    }
    districts = {_facility_district(c) for c in facility_codes if _facility_district(c)}
    bemonc = sum(1 for v in classifications.values() if v == "BEmONC")
    cemonc = sum(1 for v in classifications.values() if v == "CEmONC")

    total_births = sum(_numerators_by_facility("mnid_lab_core_totalbirths", {}, df, agg_df, start_date, end_date).values())
    caesareans = sum(_numerators_by_facility("mnid_lab_moh_035", {}, df, agg_df, start_date, end_date).values())
    live_births = sum(_numerators_by_facility("mnid_lab_overview_004", {}, df, agg_df, start_date, end_date).values())

    summary = _card([
        _section_title("Country Summary"),
        html.Div([
            _summary_stat("Facilities selected", len(facility_codes)),
            _summary_stat("Districts represented", len(districts)),
            _summary_stat("BEmONC facilities", bemonc),
            _summary_stat("CEmONC facilities", cemonc),
            _summary_stat("Total deliveries", f"{total_births:,}"),
            _summary_stat("Total caesarean deliveries", f"{caesareans:,}"),
            _summary_stat("Total newborn unit admissions", f"{live_births:,}"),
        ], style={"display": "flex", "flexWrap": "wrap", "gap": "10px"}),
    ])

    if len(facility_codes) == 1:
        code = facility_codes[0]
        detail = _card([
            _section_title(_facility_label(code)),
            html.Div(f"{_facility_district(code)} · {resolve_facility_level(code, _facility_label(code))} · {classifications[code]}",
                     style={"fontSize": "12px", "color": MUTED}),
        ])
        return html.Div([summary, detail])

    rows = [
        [
            _facility_district(code), _facility_label(code),
            resolve_facility_level(code, _facility_label(code)), classifications[code],
            _numerators_by_facility("mnid_lab_core_totalbirths", {}, df, agg_df, start_date, end_date).get(code, 0),
            _numerators_by_facility("mnid_lab_moh_035", {}, df, agg_df, start_date, end_date).get(code, 0),
            _numerators_by_facility("mnid_lab_overview_004", {}, df, agg_df, start_date, end_date).get(code, 0),
        ]
        for code in facility_codes
    ]
    table = _card([
        _section_title("Facility Comparison"),
        _data_table(
            ["District", "Facility", "Facility level", "EmONC classification",
             "Total deliveries", "Caesarean deliveries", "Newborn unit admissions"],
            rows,
        ),
    ])
    return html.Div([summary, table])


# ---------------------------------------------------------------------------
# People / Products & Commodities / Systems & Infrastructure -- awaiting data
# ---------------------------------------------------------------------------

def _awaiting_detail_table(items: list[str]) -> dash_table.DataTable:
    return _data_table(["Indicator", "Result"], [[label, "Not reported"] for label in items])


def _awaiting_comparison_table(items: list[str], facility_codes: list[str]) -> dash_table.DataTable:
    rows = [[label, len(facility_codes), "0 (0%)"] for label in items]
    return _data_table(["Indicator", "Facilities assessed, n", "Available/reported, n (%)"], rows)


def _awaiting_domain_detail_table(domain_items: list[tuple[str, str]]) -> dash_table.DataTable:
    return _data_table(["Domain", "Item", "Result"], [[d, i, "Not reported"] for d, i in domain_items])


def _awaiting_domain_comparison_table(domain_items: list[tuple[str, str]], facility_codes: list[str]) -> dash_table.DataTable:
    rows = [[d, i, len(facility_codes), "0 (0%)"] for d, i in domain_items]
    return _data_table(["Domain", "Item", "Facilities assessed, n", "Available, n (%)"], rows)


def _real_indicator_rows(indicators: list[dict], df: pd.DataFrame,
                          agg_df: pd.DataFrame | None, start_date, end_date,
                          facility_codes: list[str]) -> list[list]:
    """Render already-real indicators (supply/workforce/data-quality) the same
    row shape as the awaiting-data tables, so real and placeholder rows sit
    together in one table without the UI needing to know which is which."""
    rows = []
    for ind in indicators:
        num, den, pct = _cov(df, ind.get("numerator_filters", {}), ind.get("denominator_filters", {}))
        rows.append([ind.get("label", "Indicator"), f"{den:,}", f"{pct:.0f}%" if den else "Not reported"])
    return rows


def _people_tab(facility_codes: list[str], wf_inds: list[dict] | None, df: pd.DataFrame) -> html.Div:
    real = _real_indicator_rows(wf_inds or [], df, None, None, None, facility_codes)
    real_card = _card([
        _section_title("Workforce Competency (tracked)"),
        _data_table(["Indicator", "Assessed, n", "Result"], real) if real else html.Div(
            "No workforce competency indicators configured for this report.", style={"fontSize": "12px", "color": MUTED}),
    ])
    body = _scope_view(
        facility_codes,
        detail_fn=lambda code: html.Div([
            _card([_section_title(f"Neonatal Care Unit Staffing · {_facility_label(code)}"), _awaiting_detail_table(CADRES_NEONATAL)]),
            _card([_section_title(f"Maternity Staffing · {_facility_label(code)}"), _awaiting_detail_table(CADRES_MATERNITY)]),
        ]),
        comparison_fn=lambda codes: html.Div([
            _card([_section_title("Neonatal Care Unit Staffing · Comparison"), _awaiting_comparison_table(CADRES_NEONATAL, codes)]),
            _card([_section_title("Maternity Staffing · Comparison"), _awaiting_comparison_table(CADRES_MATERNITY, codes)]),
        ]),
    )
    return html.Div([real_card, body])


def _products_tab(facility_codes: list[str], supply_inds: list[dict] | None, df: pd.DataFrame) -> html.Div:
    real = _real_indicator_rows(supply_inds or [], df, None, None, None, facility_codes)
    real_card = _card([
        _section_title("Commodity Availability (tracked)"),
        _data_table(["Indicator", "Assessed, n", "Result"], real) if real else html.Div(
            "No commodity indicators configured for this report.", style={"fontSize": "12px", "color": MUTED}),
    ])
    body = _scope_view(
        facility_codes,
        detail_fn=lambda code: html.Div([
            _card([_section_title(f"Maternity Equipment · {_facility_label(code)}"), _awaiting_domain_detail_table(EQUIPMENT_MATERNITY)]),
            _card([_section_title(f"Maternity Essential Medicines · {_facility_label(code)}"), _awaiting_domain_detail_table(TRACER_MEDICINES_MATERNITY)]),
            _card([_section_title(f"Newborn Equipment · {_facility_label(code)}"), _awaiting_domain_detail_table(EQUIPMENT_NEWBORN)]),
            _card([_section_title(f"Newborn Tracer Medicines · {_facility_label(code)}"), _awaiting_domain_detail_table(TRACER_MEDICINES_NEWBORN)]),
        ]),
        comparison_fn=lambda codes: html.Div([
            _card([_section_title("Maternity Equipment · Comparison"), _awaiting_domain_comparison_table(EQUIPMENT_MATERNITY, codes)]),
            _card([_section_title("Newborn Equipment & Medicines · Comparison"), _awaiting_domain_comparison_table(EQUIPMENT_NEWBORN + TRACER_MEDICINES_NEWBORN, codes)]),
        ]),
    )
    return html.Div([real_card, body])


def _systems_tab(facility_codes: list[str], dq_inds: list[dict] | None, df: pd.DataFrame) -> html.Div:
    real = _real_indicator_rows(dq_inds or [], df, None, None, None, facility_codes)
    real_card = _card([
        _section_title("Data Quality (tracked)"),
        _data_table(["Indicator", "Assessed, n", "Result"], real) if real else html.Div(
            "No data-quality indicators configured for this report.", style={"fontSize": "12px", "color": MUTED}),
    ])
    body = _scope_view(
        facility_codes,
        detail_fn=lambda code: html.Div([
            _card([_section_title(f"Maternity Unit Infrastructure · {_facility_label(code)}"), _awaiting_domain_detail_table(INFRASTRUCTURE_MATERNITY)]),
            _card([_section_title(f"Neonatal Care Unit Infrastructure · {_facility_label(code)}"), _awaiting_domain_detail_table(INFRASTRUCTURE_NEONATAL)]),
            _card([_section_title(f"Referral and Transport · {_facility_label(code)}"), _awaiting_detail_table(REFERRAL_TRANSPORT)]),
            _card([_section_title(f"Data and Quality-Improvement Systems · {_facility_label(code)}"), _awaiting_detail_table(DATA_QI_SYSTEMS)]),
        ]),
        comparison_fn=lambda codes: html.Div([
            _card([_section_title("Infrastructure · Comparison"), _awaiting_domain_comparison_table(INFRASTRUCTURE_MATERNITY + INFRASTRUCTURE_NEONATAL, codes)]),
            _card([_section_title("Referral, Transport & QI Systems · Comparison"), _awaiting_comparison_table(REFERRAL_TRANSPORT + DATA_QI_SYSTEMS, codes)]),
        ]),
    )
    return html.Div([real_card, body])


# ---------------------------------------------------------------------------
# Lazy sub-tab shell (same pattern as mnid/dashboards/MNH-Nest360/layout.py)
# ---------------------------------------------------------------------------

_TABS = [
    ("overview", "Overview"),
    ("signal-functions", "Signal Functions"),
    ("people", "People"),
    ("products", "Products & Commodities"),
    ("systems", "Systems & Infrastructure"),
]


def _render_tab_content(tab_value: str, stored: dict) -> html.Div:
    df = _restore_ui_dataframe(stored.get("data_key"))
    facility_codes = stored.get("facility_codes") or _facility_universe(df)
    start_date = stored.get("start_date")
    end_date = stored.get("end_date")
    agg_df = _get_aggregate()

    if tab_value == "overview":
        return _build_overview_tab(facility_codes, df, agg_df, start_date, end_date)
    if tab_value == "signal-functions":
        return _build_signal_functions_tab(facility_codes, df, agg_df, start_date, end_date)
    if tab_value == "people":
        return _people_tab(facility_codes, stored.get("wf_inds"), df)
    if tab_value == "products":
        return _products_tab(facility_codes, stored.get("supply_inds"), df)
    if tab_value == "systems":
        return _systems_tab(facility_codes, stored.get("dq_inds"), df)
    return html.Div()


@callback(
    Output("oprd-tab-container", "children"),
    Input("oprd-subtabs", "value"),
    State("oprd-store", "data"),
)
def _oprd_sync_tab(tab_value, stored):
    if not tab_value or not stored:
        raise PreventUpdate
    return _render_tab_content(tab_value, stored)


def render_operational_readiness(
    df: pd.DataFrame,
    supply_inds: list[dict] | None = None,
    wf_inds: list[dict] | None = None,
    dq_inds: list[dict] | None = None,
    scope_meta: dict | None = None,
    start_date=None,
    end_date=None,
) -> html.Div:
    facility_codes = _facility_universe(df)
    store_data = {
        "data_key": _remember_ui_payload("oprd", df if df is not None else pd.DataFrame()),
        "facility_codes": facility_codes,
        "start_date": str(start_date) if start_date else None,
        "end_date": str(end_date) if end_date else None,
        "supply_inds": supply_inds or [],
        "wf_inds": wf_inds or [],
        "dq_inds": dq_inds or [],
    }
    default_tab = _TABS[0][0]
    initial_content = _render_tab_content(default_tab, store_data)

    return html.Div(className="mnid-executive-page", children=[
        dcc.Store(id="oprd-store", data=store_data),
        dcc.Tabs(
            id="oprd-subtabs",
            value=default_tab,
            children=[dcc.Tab(label=label, value=value) for value, label in _TABS],
            style={"marginBottom": "16px"},
        ),
        dcc.Loading(
            html.Div(id="oprd-tab-container", children=initial_content),
            type="circle", color=GREEN,
        ),
    ])
