"""Generate MNID Developer Guide PDF."""
import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Preformatted,
    HRFlowable, Table, TableStyle, PageBreak,
)
from reportlab.lib.enums import TA_JUSTIFY

# ── palette ───────────────────────────────────────────────────────────────────
GREEN       = colors.HexColor('#15803D')
GREEN_LIGHT = colors.HexColor('#F0FDF4')
GREEN_DARK  = colors.HexColor('#065F46')
SLATE       = colors.HexColor('#0F172A')
SLATE_MED   = colors.HexColor('#334155')
SLATE_DIM   = colors.HexColor('#64748B')
SLATE_MUT   = colors.HexColor('#94A3B8')
BORDER      = colors.HexColor('#E2E8F0')
CODE_BG     = colors.HexColor('#F8FAFC')
AMBER       = colors.HexColor('#D97706')
AMBER_LIGHT = colors.HexColor('#FEF3C7')
BLUE        = colors.HexColor('#2563EB')
BLUE_LIGHT  = colors.HexColor('#EFF6FF')

# ── style helpers ─────────────────────────────────────────────────────────────
def S(name, **kw):
    return ParagraphStyle(name, **kw)

H1   = S('H1',   fontSize=26, leading=32, textColor=SLATE,      fontName='Helvetica-Bold', spaceAfter=8)
H2   = S('H2',   fontSize=17, leading=22, textColor=GREEN_DARK,  fontName='Helvetica-Bold', spaceBefore=18, spaceAfter=6)
H3   = S('H3',   fontSize=13, leading=18, textColor=SLATE,       fontName='Helvetica-Bold', spaceBefore=12, spaceAfter=4)
H4   = S('H4',   fontSize=11, leading=16, textColor=SLATE_MED,   fontName='Helvetica-Bold', spaceBefore=8,  spaceAfter=3)
BODY = S('BODY', fontSize=10, leading=16, textColor=SLATE_MED,   fontName='Helvetica',      spaceAfter=6,   alignment=TA_JUSTIFY)
BDYL = S('BDYL', fontSize=10, leading=16, textColor=SLATE_MED,   fontName='Helvetica',      spaceAfter=4)
NOTE = S('NOTE', fontSize=9,  leading=14, textColor=SLATE_DIM,   fontName='Helvetica-Oblique', spaceAfter=4)
CODE = S('CODE', fontSize=8,  leading=12, textColor=SLATE,       fontName='Courier',
         backColor=CODE_BG, spaceAfter=6, leftIndent=8, rightIndent=8, spaceBefore=4)
SUB  = S('SUB',  fontSize=13, leading=18, textColor=SLATE_DIM,   fontName='Helvetica',      spaceAfter=4)
TOC  = S('TOC',  fontSize=11, leading=20, textColor=SLATE_MED,   fontName='Helvetica',      leftIndent=0.5*cm)

def hr(c=BORDER, t=0.5, sp=8):
    return HRFlowable(width='100%', thickness=t, color=c, spaceAfter=sp, spaceBefore=sp)

def box(text, title, bg, border_c, title_c):
    data = [[Paragraph(f'<b>{title}</b>', S('BT', fontSize=10, leading=14,
                        textColor=title_c, fontName='Helvetica-Bold')),
             Paragraph(text, BDYL)]]
    t = Table(data, colWidths=[2.4*cm, None])
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (-1,-1), bg),
        ('GRID',         (0,0), (-1,-1), 0.5, border_c),
        ('TOPPADDING',   (0,0), (-1,-1), 6),
        ('BOTTOMPADDING',(0,0), (-1,-1), 6),
        ('LEFTPADDING',  (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
    ]))
    return t

def tip(text):  return box(text, 'Tip',  GREEN_LIGHT, GREEN, GREEN_DARK)
def warn(text): return box(text, 'Note', AMBER_LIGHT, AMBER, AMBER)
def info(text): return box(text, 'Info', BLUE_LIGHT,  BLUE,  BLUE)

def code(text):
    return Preformatted(text, CODE)

def bullets(items, indent=0.5):
    st = S('BUL', fontSize=10, leading=16, textColor=SLATE_MED,
           fontName='Helvetica', leftIndent=indent*cm, spaceAfter=3)
    return [Paragraph(f'• {it}', st) for it in items]

def numbered(items, indent=0.5):
    return [Paragraph(f'{i+1}.  {it}',
                      S(f'N{i}', fontSize=10, leading=16, textColor=SLATE_MED,
                        fontName='Helvetica', leftIndent=indent*cm, spaceAfter=3))
            for i, it in enumerate(items)]

def tbl(headers, rows, widths=None):
    th_s = S('TH', fontSize=9, leading=12, textColor=colors.white,  fontName='Helvetica-Bold')
    td_s = S('TD', fontSize=9, leading=13, textColor=SLATE_MED,     fontName='Helvetica')
    data = [[Paragraph(h, th_s) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), td_s) for c in row])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (-1,0),  GREEN),
        ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, CODE_BG]),
        ('GRID',         (0,0), (-1,-1), 0.4, BORDER),
        ('TOPPADDING',   (0,0), (-1,-1), 5),
        ('BOTTOMPADDING',(0,0), (-1,-1), 5),
        ('LEFTPADDING',  (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('VALIGN',       (0,0), (-1,-1), 'TOP'),
    ]))
    return t

# ═══════════════════════════════════════════════════════════════════════════════
story = []

# COVER
story += [
    Spacer(1, 2.5*cm),
    Paragraph('MNID Dashboard', H1),
    Paragraph('Developer Guide', SUB),
    Spacer(1, 0.4*cm),
    hr(GREEN, t=2, sp=4),
    Spacer(1, 0.3*cm),
    Paragraph(
        'A beginner-friendly walkthrough of how the Maternal and Neonatal '
        'Indicator Dashboard works — how data flows, how tabs are built, '
        'and how to add your own dashboards without touching existing code.',
        BODY),
    Spacer(1, 0.5*cm),
    Paragraph('<b>Who is this for?</b>', H4),
    Paragraph(
        'Junior engineers and beginners who are new to the codebase. '
        'No deep Python experience required — just basic Python and an '
        'understanding of what a web dashboard is.',
        BODY),
    Spacer(1, 6*cm),
    Paragraph('MAHIS Reports — Internal Technical Documentation', NOTE),
    Paragraph('June 2026', NOTE),
    PageBreak(),
]

# TOC
story += [Paragraph('Contents', H2), hr()]
toc = [
    ('1.', 'What is MNID?'),
    ('2.', 'The Folder Map'),
    ('3.', 'How Data Flows — From Database to Chart'),
    ('4.', 'Key Concepts You Need to Know'),
    ('5.', 'The Dashboard Tabs'),
    ('6.', 'Run Charts — How They Work'),
    ('7.', 'The Indicator System'),
    ('8.', 'Callbacks — Making Things Interactive'),
    ('9.', 'The Aggregation Engine — Why Charts Are Fast'),
    ('10.', 'Adding a New Dashboard'),
    ('11.', 'Troubleshooting Common Problems'),
    ('12.', 'Quick Reference'),
]
for num, title in toc:
    story.append(Paragraph(f'<b>{num}</b>&nbsp;&nbsp;&nbsp;{title}', TOC))
story += [Spacer(1, 0.5*cm), PageBreak()]

# 1 — WHAT IS MNID
story += [
    Paragraph('1. What is MNID?', H2), hr(),
    Paragraph(
        'MNID stands for <b>Maternal and Neonatal Indicator Dashboard</b>. '
        'It is the main analytical view in the MAHIS application. '
        'Its job is to show health workers and programme managers how well '
        'maternal and newborn care services are performing at Malawi clinics.',
        BODY),
    Spacer(1, 0.3*cm),
    Paragraph('In plain language, it answers questions like:', BDYL),
    *bullets([
        'What percentage of mothers had their blood pressure measured during ANC?',
        'Are we meeting the 80% target for vitamin K given to newborns?',
        'Which districts are falling behind this month?',
        'How has the coverage trend changed over the last six months?',
    ]),
    Spacer(1, 0.3*cm),
    Paragraph('How users see it', H3),
    Paragraph(
        'The dashboard has a tab bar at the top: <b>Country Profile</b>, '
        '<b>Operational Readiness</b>, <b>Maternal</b>, and <b>Newborn</b>. '
        'Inside the Maternal and Newborn tabs there are section tabs: '
        'Overview, Coverage, Run Charts, District Performance, '
        'Geographic Coverage, and Facility Comparison.',
        BODY),
    Spacer(1, 0.4*cm),
    tip('Think of MNID as a self-contained mini-app living inside the larger '
        'MAHIS web application. It has its own data pipeline, its own layout '
        'builders, and its own Dash callbacks.'),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 2 — FOLDER MAP
story += [
    Paragraph('2. The Folder Map', H2), hr(),
    Paragraph(
        'All MNID code lives inside the <b>mnid/</b> folder. '
        'It is organised into sub-packages by responsibility.',
        BODY),
    Spacer(1, 0.3*cm),
    code(
'''mnid/
├── app.py                ← entry point (re-exports everything)
│
├── core/                 ← foundational layer, no charts, no callbacks
│   ├── constants.py      ← colours, palettes, facility names/districts
│   ├── cache.py          ← disk cache, in-memory caches, scope helpers
│   ├── data_utils.py     ← cleans raw parquet into analysis-ready DataFrame
│   └── indicators.py     ← defines what each indicator measures
│
├── charts/               ← building blocks for visualisations
│   ├── chart_helpers.py  ← moving average, colour helpers, coverage %
│   ├── heatmap.py        ← heatmap tables and the Malawi geo map
│   ├── coverage.py       ← coverage bar charts, gauges, comparison section
│   ├── layout.py         ← hero donut cards, KPI rows, sidebar, topbar
│   └── geo_utils.py      ← GeoJSON loading and facility positioning
│
├── views/                ← dashboard assembly and Dash callbacks
│   ├── kpi_engine.py     ← computes indicator values, builds dashboard
│   ├── trends.py         ← run chart figures and the trends section
│   ├── service_table.py  ← service snapshot table/chart
│   ├── callbacks.py      ← heatmap, comparison, performance callbacks
│   └── renderer.py       ← render_mnid_dashboard(), tab loading
│
├── aggregation/          ← pre-built fast data store
│   ├── engine.py         ← builds indicator_aggregates.parquet overnight
│   ├── scheduler.py      ← schedules the nightly build
│   └── store.py          ← loads and queries the parquet file
│
├── components/           ← reusable UI components
│   ├── run_charts.py     ← _run_chart(), card builder, grain bucketing
│   └── country_profile_trends.py
│
└── dashboards/           ← put your NEW dashboards here'''),
    Spacer(1, 0.4*cm),
    info('The <b>core/</b> folder is the foundation — it never imports from '
         '<b>charts/</b> or <b>views/</b>. Data always flows upward: '
         'core → charts → views.'),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 3 — DATA FLOW
story += [
    Paragraph('3. How Data Flows — From Database to Chart', H2), hr(),
    Paragraph(
        'Every time a user loads the maternal dashboard, the following '
        'sequence of steps happens. This is the most important thing '
        'to understand as a new developer.',
        BODY),
    Spacer(1, 0.3*cm),
    *numbered([
        '<b>User opens the dashboard tab</b> — The browser sends a Dash '
        'callback to the server requesting the maternal dashboard content.',

        '<b>Raw data is loaded</b> — <font face="Courier">pages/home.py</font> '
        'queries the parquet file (1.7 million rows) and keeps only '
        'MCH-related rows (~8 000 rows). This is called <font face="Courier">data_opd</font>.',

        '<b>data_opd is prepared</b> — '
        '<font face="Courier">mnid/core/data_utils.py → prepare_mnid_dataframe()</font> '
        'cleans the data: normalises column names, aliases concept names '
        '("VItamin K Given?" → "Vitamin K given"), derives person-level flags, '
        'and registers facility names. The result is <font face="Courier">network_df</font>.',

        '<b>Indicators are computed</b> — '
        '<font face="Courier">mnid/views/kpi_engine.py → _build_mnid_indicator_content()</font> '
        'reads each indicator definition, counts numerator and denominator '
        'patients, and calculates coverage %. Example: "Blood pressure measured" '
        '= rows where BP was recorded / all ANC clients × 100.',

        '<b>Sections are built</b> — Coverage charts, run charts, heatmaps, '
        'and comparison charts are assembled as Dash HTML components. '
        'Each builder lives in <font face="Courier">mnid/charts/</font>.',

        '<b>Dashboard is returned</b> — The assembled HTML tree is sent to '
        'the browser. The user sees the dashboard.',

        '<b>Interactive callbacks fire</b> — When the user clicks a category '
        'button or changes the grain dropdown, a Dash callback re-queries the '
        'aggregate store and re-renders only the affected section.',
    ]),
    Spacer(1, 0.4*cm),
    Paragraph('The two data sources', H3),
    tbl(
        ['Source', 'What it is', 'When used'],
        [
            ['network_df',
             'Cleaned live rows from the parquet file',
             'Initial render; fallback when aggregate is missing'],
            ['indicator_aggregates.parquet',
             'Pre-built summary: one row per indicator × facility × month',
             'Interactive callbacks — fast, no row scanning'],
        ],
        widths=[3.5*cm, 7.5*cm, 6*cm],
    ),
    Spacer(1, 0.4*cm),
    warn('The aggregate parquet is built overnight. If you start the app for '
         'the first time with no aggregate, the first load is slow. '
         'After it is built, all callbacks are fast.'),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 4 — KEY CONCEPTS
story += [
    Paragraph('4. Key Concepts You Need to Know', H2), hr(),

    Paragraph('Indicators', H3),
    Paragraph(
        'An <b>indicator</b> is the core unit of measurement. Every chart, '
        'badge, and table is driven by indicators. An indicator is defined '
        'by two filters: a <b>numerator filter</b> (who counts as positive) '
        'and a <b>denominator filter</b> (the total eligible population).',
        BODY),
    code(
'''# Example indicator (from mnid/core/indicators.py)
{
    "id":    "mnid-anc-bp",
    "label": "Blood pressure measured",
    "category": "ANC",
    "target": 80,                     # 80% target
    "numerator_filters": {
        "unique":    "person_id",
        "variable1": "concept_name",
        "value1":    "Blood pressure measured",
    },
    "denominator_filters": {
        "unique":    "person_id",
        "variable1": "concept_name",
        "value1":    "ANC visit",     # all ANC clients
    },
}'''),
    tip('Think of an indicator as a fraction: numerator / denominator. '
        'The numerator filter picks the "positive" rows. '
        'The denominator filter picks the total eligible pool.'),

    Spacer(1, 0.3*cm),
    Paragraph('Categories', H3),
    Paragraph(
        'Indicators are grouped into four <b>categories</b>: '
        '<b>ANC</b> (Antenatal Care), <b>Labour</b> (Labour and Delivery), '
        '<b>PNC</b> (Postnatal Care), and <b>Newborn</b>.',
        BODY),

    Spacer(1, 0.3*cm),
    Paragraph('Coverage %', H3),
    Paragraph(
        'Coverage % = (numerator count / denominator count) × 100, capped at 100%. '
        'A coverage of 76% means 76 out of every 100 eligible patients had '
        'the indicator recorded as positive.',
        BODY),

    Spacer(1, 0.3*cm),
    Paragraph('Scope', H3),
    Paragraph(
        'The <b>scope</b> is what the user has filtered to — which facilities, '
        'districts, date range, and programme category. It travels through '
        'the pipeline as a Python dictionary called '
        '<font face="Courier">scope_meta</font>.',
        BODY),
    code(
'''scope_meta = {
    "level":               "national",   # national | district | facility
    "selected_facilities": [],
    "selected_districts":  [],
    "mnid_categories":     ["ANC"],      # which programme to show
    "dataset_version":     "v2",
}'''),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 5 — DASHBOARD TABS
story += [
    Paragraph('5. The Dashboard Tabs', H2), hr(),
    tbl(
        ['Tab', 'What it shows', 'Where it is built'],
        [
            ['Country Profile',
             'National summary: births, mortality, coverage trends over time',
             'mnid/views/executive_views.py → render_country_profile()'],
            ['Operational Readiness',
             'Supply, workforce, and data quality indicators per facility',
             'mnid/views/executive_views.py → render_operational_readiness()'],
            ['Maternal',
             'ANC, Labour, PNC coverage, run charts, heatmaps, comparison',
             'mnid/views/kpi_engine.py → _build_mnid_indicator_content()'],
            ['Newborn',
             'Same structure as Maternal but for Newborn indicators',
             'Same function, different config and scope_meta'],
        ],
        widths=[3.5*cm, 6.5*cm, 7*cm],
    ),
    Spacer(1, 0.4*cm),
    Paragraph('How a tab loads', H3),
    Paragraph(
        'When the user clicks a tab, the callback '
        '<font face="Courier">_render_mnid_executive_tab</font> in '
        '<font face="Courier">mnid/views/renderer.py</font> fires. '
        'It dispatches to the right builder function and puts the result '
        'into the <font face="Courier">mnid-executive-content</font> div.',
        BODY),
    code(
'''# Simplified — what happens when "Maternal" tab is clicked
def _build_executive_tab_view(selected, views, state):
    if selected == "maternal-dashboard":
        bundle = _build_mnid_indicator_content(
            network_df  = prepared DataFrame,
            config      = dashboard JSON config,
            start_date  = filter start,
            end_date    = filter end,
            scope_meta  = facilities / districts / categories,
        )
        return bundle["indicator_content"]   # the full HTML layout'''),
    Spacer(1, 0.4*cm),
    info('The Maternal and Newborn tabs are <b>not</b> cached to disk. '
         'This ensures interactive callbacks always have fresh data in memory.'),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 6 — RUN CHARTS
story += [
    Paragraph('6. Run Charts — How They Work', H2), hr(),
    Paragraph(
        'Run charts show indicator coverage over time as a smoothed line. '
        'They answer: "Is this indicator getting better or worse?"',
        BODY),
    Spacer(1, 0.3*cm),
    Paragraph('The section controls', H3),
    *bullets([
        'Category buttons — switch between ANC / Labour / PNC / Newborn',
        'Indicator dropdown — pick which indicators to show (multi-select)',
        'Location dropdown — all facilities or a specific one',
        'Grain dropdown — Weekly / Monthly / Quarterly / Yearly',
    ]),
    Spacer(1, 0.3*cm),
    Paragraph('Inside a chart card', H3),
    Paragraph(
        'Each card is a plain white <font face="Courier">mnid-chart-card</font> div. '
        'It shows the indicator label, a coloured target badge (green = on target, '
        'amber = close, red = below), and a Plotly figure built by '
        '<font face="Courier">_indicator_run_fig()</font>.',
        BODY),
    code(
'''# What _indicator_run_fig() draws on each chart:
#
# 1. A dotted target line  (e.g. 80% — grey dashed)
# 2. A spline line         — the MOVING AVERAGE of coverage
# 3. A filled area         — below the line, same colour at 8% opacity
# 4. Two text labels       — start % and end % of the period
# 5. A "target X%" label   — pinned to the right edge
#
# Hover tooltip (unified — shows all values at the hovered period):
#   Moving avg: 73.4%
#   Actual:     75.0%   ← the raw (non-smoothed) period coverage
#   Clients: 142 / 189  ← numerator / denominator'''),
    Spacer(1, 0.3*cm),
    Paragraph('Fast path vs slow path', H3),
    Paragraph(
        'The run chart first tries the fast path: query the aggregate parquet '
        '(milliseconds). If the aggregate does not have data for this indicator, '
        'it falls back to scanning the raw DataFrame (slower).',
        BODY),
    tip('If run charts appear empty, it usually means the aggregate was built '
        'from demo data but the app is now using live data. '
        'Delete data/mnid_aggregates/indicator_aggregates.parquet and restart '
        'to trigger a rebuild.'),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 7 — INDICATOR SYSTEM
story += [
    Paragraph('7. The Indicator System', H2), hr(),
    Paragraph(
        'Indicators are defined in '
        '<font face="Courier">mnid/core/indicators.py</font> '
        'in the function '
        '<font face="Courier">_program_based_priority_indicators()</font>.',
        BODY),
    code(
'''# Every indicator dict has these fields:
{
    "id":                  "mnid-anc-bp",   # unique key
    "label":               "Blood pressure measured",
    "category":            "ANC",
    "target":              80,
    "status":              "tracked",       # see table below
    "numerator_filters":   { ... },
    "denominator_filters": { ... },
    # These are computed at render time:
    "pct":                 73.4,
    "numerator":           142,
    "denominator":         189,
    "delta_pct":           +2.1,            # change vs previous period
}'''),
    Spacer(1, 0.3*cm),
    tbl(
        ['Status', 'Meaning'],
        [
            ['tracked', 'Actively monitored — shown in all sections'],
            ['awaiting_baseline', 'Not enough data yet — counted in the overview but not charted'],
            ['overview_only', 'Summary stats (e.g. total ANC clients) — shown in hero cards only'],
        ],
        widths=[4.5*cm, 12.5*cm],
    ),
    Spacer(1, 0.4*cm),
    Paragraph('Adding a new indicator', H3),
    Paragraph(
        'Open <font face="Courier">mnid/core/indicators.py</font>, find the '
        'right category list inside <font face="Courier">_program_based_priority_indicators()</font>, '
        'and add a new dict. Minimum required fields: '
        '<font face="Courier">id</font>, <font face="Courier">label</font>, '
        '<font face="Courier">category</font>, '
        '<font face="Courier">numerator_filters</font>, '
        '<font face="Courier">denominator_filters</font>.',
        BODY),
    tip('After adding an indicator, rebuild the aggregate parquet so the '
        'fast query path includes it. Otherwise it falls back to slower '
        'row scanning.'),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 8 — CALLBACKS
story += [
    Paragraph('8. Callbacks — Making Things Interactive', H2), hr(),
    Paragraph(
        'Dash callbacks are Python functions that run on the server when '
        'the user interacts with the browser. They are marked with the '
        '<font face="Courier">@callback</font> decorator.',
        BODY),
    code(
'''from dash import callback, Input, Output, State

@callback(
    Output("some-component", "children"),   # what to update
    Input("a-dropdown", "value"),           # what triggers the update
    State("a-store", "data"),               # read-only, does NOT trigger
)
def my_callback(dropdown_value, store_data):
    # do something
    return new_content'''),
    Spacer(1, 0.3*cm),
    info('A <b>State</b> is different from an <b>Input</b>. Changing a State '
         'does NOT trigger the callback — it only provides extra data '
         'when the callback fires because of an Input change.'),
    Spacer(1, 0.4*cm),
    Paragraph('Where the MNID callbacks live', H3),
    tbl(
        ['File', 'Callbacks inside'],
        [
            ['mnid/views/trends.py',
             'update_trend_chart — redraws run chart cards when category, grain, or location changes'],
            ['mnid/views/callbacks.py',
             'update_heatmap_view, update_compare_charts, update_performance_heatmap'],
            ['mnid/views/renderer.py',
             '_render_mnid_executive_tab, _preload_mnid_executive_tabs, _update_country_profile_chart_grain'],
            ['mnid/views/service_table.py',
             'update_service_table — switches between table and chart view'],
        ],
        widths=[5.5*cm, 11.5*cm],
    ),
    Spacer(1, 0.4*cm),
    Paragraph('The dcc.Store pattern', H3),
    Paragraph(
        'MNID stores large data (DataFrames, indicator lists) in server memory '
        'keyed by a short string called <font face="Courier">data_key</font>. '
        'The browser holds only this key in a '
        '<font face="Courier">dcc.Store</font> component. '
        'When a callback needs the data it calls '
        '<font face="Courier">_restore_ui_dataframe(data_key)</font>.',
        BODY),
    tip('This keeps browser payloads small. Only string keys travel over '
        'the network; the actual DataFrames stay on the server.'),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 9 — AGGREGATION ENGINE
story += [
    Paragraph('9. The Aggregation Engine — Why Charts Are Fast', H2), hr(),
    Paragraph(
        'Scanning 1.7 million raw rows on every dropdown change would be '
        'unusably slow. The aggregation engine solves this by pre-computing '
        'every indicator for every facility and time period and storing the '
        'result as a compact parquet file.',
        BODY),
    Spacer(1, 0.3*cm),
    code(
'''# indicator_aggregates.parquet — structure:
# indicator_id | grain   | period_start | facility_code | numerator | denominator | pct
# --------------------------------------------------------------------------------------
# mnid-anc-bp  | monthly | 2026-05-01   | FAC001        | 142       | 189         | 75.1
# mnid-anc-bp  | monthly | 2026-06-01   | FAC001        | 161       | 201         | 80.1'''),
    Spacer(1, 0.3*cm),
    Paragraph('Rebuilding the aggregate', H3),
    code(
'''# Run in a Python terminal or schedule it nightly:
from mnid.aggregation.scheduler import run_aggregation_job

run_aggregation_job()                    # all grains: daily, weekly, monthly...
run_aggregation_job(grains=["monthly"])  # monthly only (faster, used at startup)'''),
    Spacer(1, 0.4*cm),
    warn('The aggregate is tied to the data it was built from. If you switch '
         'between demo and live data, delete '
         'data/mnid_aggregates/indicator_aggregates.parquet and rebuild.'),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 10 — ADDING A NEW DASHBOARD
story += [
    Paragraph('10. Adding a New Dashboard', H2), hr(),
    Paragraph(
        'The <font face="Courier">mnid/dashboards/</font> folder is reserved '
        'for new dashboards. You can create one without touching any existing '
        'file. Here is a complete walkthrough.',
        BODY),
    Spacer(1, 0.3*cm),
    Paragraph('Step 1 — Create the dashboard module', H3),
    code(
'''# mnid/dashboards/nutrition.py

from mnid.core.data_utils  import prepare_mnid_dataframe
from mnid.core.indicators  import _resolve_runtime_mnid_indicators
from mnid.charts.layout    import _kpi_row, _section_anchor
from mnid.views.trends     import _trend_switcher
from dash import html

MY_INDICATORS = [
    {
        "id":    "nutrition-wasting",
        "label": "Children screened for wasting",
        "category": "Nutrition",
        "target": 75,
        "status": "tracked",
        "numerator_filters":   {
            "unique":    "person_id",
            "variable1": "concept_name",
            "value1":    "Wasting screening",
        },
        "denominator_filters": {
            "unique":    "person_id",
            "variable1": "concept_name",
            "value1":    "Under-5 visit",
        },
    },
    # add more indicators here ...
]

def render_nutrition_dashboard(data_opd, config, facility_code,
                                start_date, end_date, scope_meta=None):
    network_df = prepare_mnid_dataframe(data_opd)
    indicators = _resolve_runtime_mnid_indicators(
        MY_INDICATORS, network_df
    )
    return html.Div([
        _section_anchor("nutrition-summary"),
        html.H2("Nutrition Dashboard"),
        _kpi_row(indicators),
        _trend_switcher(network_df, indicators),
    ])'''),
    Spacer(1, 0.3*cm),
    Paragraph('Step 2 — Register a Dash page', H3),
    code(
'''# pages/nutrition.py
import dash
from dash import html, callback, Input, Output
from mnid.dashboards.nutrition import render_nutrition_dashboard

dash.register_page(__name__, path="/nutrition", name="Nutrition")
layout = html.Div(id="nutrition-content")

@callback(Output("nutrition-content", "children"), Input("url", "pathname"))
def render(pathname):
    if pathname != "/nutrition":
        raise dash.exceptions.PreventUpdate
    # ... load data_opd same way as pages/home.py ...
    return render_nutrition_dashboard(data_opd, config, ...)'''),
    Spacer(1, 0.3*cm),
    Paragraph('Step 3 — Add a nav link', H3),
    code(
'''# helpers/navigation_callbacks.py  →  inside _build_nav()
dbc.NavLink("Nutrition", href="/nutrition"),'''),
    Spacer(1, 0.4*cm),
    tip('You never need to edit mnid/app.py, mnid/views/kpi_engine.py, or '
        'any existing dashboard file. Your new dashboard is completely '
        'self-contained in mnid/dashboards/.'),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 11 — TROUBLESHOOTING
story += [
    Paragraph('11. Troubleshooting Common Problems', H2), hr(),
    tbl(
        ['Symptom', 'Likely cause', 'Fix'],
        [
            ['Run charts show nothing',
             'Aggregate is stale (demo vs live mismatch)',
             'Delete data/mnid_aggregates/indicator_aggregates.parquet and restart'],
            ['Newborn tab disappeared',
             'Config path wrong after sub-package nesting',
             'Fixed — _load_mnid_report_config() now uses parents[2]. Restart.'],
            ['Maternal tab blank after restart',
             'Old disk-cached view without in-memory data',
             'Fixed — maternal/newborn tabs now bypass disk cache on load.'],
            ['Facility comparison shows nothing',
             'Aggregate discarded + empty UI cache',
             'Rebuild the aggregate with live data (see Section 9)'],
            ['Hover shows only one value',
             'Old hovertemplate without raw coverage field',
             'Fixed — _indicator_run_fig() now passes raw ys as customdata[3]'],
            ['App takes 60+ seconds on first load',
             'Aggregate not built yet',
             'Normal on first run. Monthly grain builds in ~20 seconds in background.'],
        ],
        widths=[4.5*cm, 5*cm, 7.5*cm],
    ),
    Spacer(1, 0.5*cm),
    Paragraph('Clearing the cache manually', H3),
    code(
'''# Run in a Python terminal while the server is stopped:
from mnid.core.cache import (
    _MNID_EXECUTIVE_DISK_CACHE, _worker_view_cache, _network_df_cache
)
_MNID_EXECUTIVE_DISK_CACHE.clear()
_worker_view_cache.clear()
_network_df_cache.clear()
print("All caches cleared — restart the server")'''),
    Spacer(1, 0.5*cm), PageBreak(),
]

# 12 — QUICK REFERENCE
story += [
    Paragraph('12. Quick Reference', H2), hr(),
    Paragraph('Key functions', H3),
    tbl(
        ['Function', 'Location', 'What it does'],
        [
            ['prepare_mnid_dataframe(df)',
             'mnid/core/data_utils.py',
             'Cleans raw OPD rows into analysis-ready network_df'],
            ['_resolve_runtime_mnid_indicators(inds, df)',
             'mnid/core/indicators.py',
             'Resolves and computes coverage for each indicator'],
            ['_build_mnid_indicator_content(...)',
             'mnid/views/kpi_engine.py',
             'Assembles the full maternal/newborn dashboard HTML'],
            ['render_mnid_dashboard(data_opd, config, ...)',
             'mnid/views/renderer.py',
             'Top-level entry point — call this from a new page'],
            ['_trend_switcher(df, indicators, ...)',
             'mnid/views/trends.py',
             'Builds the run charts section with all controls'],
            ['get_aggregate()',
             'mnid/aggregation/store.py',
             'Returns the pre-built parquet DataFrame (None if not built)'],
            ['query_time_series(agg, id, grain, ...)',
             'mnid/aggregation/store.py',
             'Returns period-by-period coverage from the aggregate'],
        ],
        widths=[5.5*cm, 5*cm, 6.5*cm],
    ),
    Spacer(1, 0.4*cm),
    Paragraph('Key Dash component IDs', H3),
    tbl(
        ['Component ID', 'What it is'],
        [
            ['mnid-executive-content', 'The div that holds the current tab content'],
            ['mnid-executive-tabs', 'The top tab bar (Country Profile / Maternal / Newborn)'],
            ['mnid-run-charts-container', 'The div filled with run chart cards'],
            ['mnid-trend-store', 'dcc.Store holding tracked indicators and data_key'],
            ['mnid-trend-grain', 'Grain dropdown (weekly / monthly / quarterly / yearly)'],
            ['mnid-trend-location', 'Location filter dropdown'],
            ['mnid-compare-store', 'dcc.Store for facility comparison data'],
            ['mnid-heatmap-store', 'dcc.Store for heatmap / geo map data'],
        ],
        widths=[5.5*cm, 11.5*cm],
    ),
    Spacer(1, 0.4*cm),
    Paragraph('Import cheat sheet', H3),
    code(
'''# Most common imports for new dashboards:
from mnid.core.data_utils   import prepare_mnid_dataframe
from mnid.core.indicators   import _resolve_runtime_mnid_indicators
from mnid.core.constants    import OK_C, WARN_C, DANGER_C, CAT_PALETTES
from mnid.charts.layout     import _kpi_row, _hero_donut_row, _section_anchor
from mnid.charts.coverage   import _coverage_charts_section
from mnid.views.trends      import _trend_switcher
from mnid.views.renderer    import render_mnid_dashboard
from mnid.aggregation.store import get_aggregate, query_coverage, query_time_series'''),
    Spacer(1, 0.5*cm),
    hr(GREEN, t=1),
    Spacer(1, 0.3*cm),
    Paragraph('End of document — MAHIS Reports, June 2026', NOTE),
]

# ── BUILD ─────────────────────────────────────────────────────────────────────
out = Path(__file__).resolve().parents[1] / 'docs' / 'MNID_Developer_Guide.pdf'
out.parent.mkdir(exist_ok=True)

doc = SimpleDocTemplate(
    str(out),
    pagesize=A4,
    leftMargin=2.2*cm, rightMargin=2.2*cm,
    topMargin=2.2*cm, bottomMargin=2.2*cm,
    title='MNID Developer Guide',
    author='MAHIS Reports',
)
doc.build(story)
print(f'PDF written: {out}')
