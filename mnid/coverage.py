"""
MNID coverage, analysis, and comparison section builders.

Contains indicator coverage cards, phase gauges, clinical donut charts,
accordion sections, per-service-area analysis charts, system readiness,
comparative analysis, and the main coverage heatmap section layout.
"""
import pandas as pd
import plotly.graph_objects as go
import logging
from dash import html, dcc
import dash_mantine_components as dmc

from mnid.constants import (
    OK_C, WARN_C, DANGER_C, INFO_C, MUTED, GRID_C, BG, BORDER, TEXT, DIM, FONT,
    CAT_PALETTES,
    FACILITY_DISTRICT as _FACILITY_DISTRICT,
    ALL_FACILITIES as _ALL_FACILITIES,
    ALL_DISTRICTS as _ALL_DISTRICTS,
    FACILITY_NAMES as _FACILITY_NAMES,
)
from mnid.chart_helpers import (
    _CHART_LAYOUT, _TREND_ACCENT, _CAT_LABELS,
    _cov, _css, _display_pct, _value_counts, _monthly_visits,
    _chart_card, _donut, _hbar, _line,
    _monthly_concept_rate, _monthly_concept_mix_fig, _concept_rate,
    CHART_HEIGHT_SM, CHART_HEIGHT_MD, CHART_HEIGHT_LG,
    _clamp_chart_height, _graph_style, _graph_scroll_wrap,
)
from mnid.heatmap import (
    _cov_color,
    _compute_heatmap_store,
    _build_heatmap_fig,
    _build_malawi_panel,
    _build_facility_performance_heatmap_fig,
    _build_performance_attention_table,
)
from mnid.indicators import _resolve_category_order
from mnid.data_utils import (
    serialize_store_df as _serialize_store_df,
    _remember_ui_payload,
)


_LOGGER = logging.getLogger(__name__)


# Newborn helpers (used by _newborn_charts)

def _newborn_summary_card(label, num, den, pct, accent, note):
    return html.Div(className='mnid-newborn-metric', style={'--nb-accent': accent}, children=[
        html.Div(label, className='mnid-newborn-metric-label'),
        html.Div([
            html.Span(f'{_display_pct(pct):.0f}%', className='mnid-newborn-metric-value'),
            html.Span(f'{num}/{den}', className='mnid-newborn-metric-meta'),
        ], className='mnid-newborn-metric-top'),
        html.Div(note, className='mnid-newborn-metric-note'),
    ])


def _newborn_section_card(title, subtitle, tone, children):
    return html.Div(className=f'mnid-chart-card mnid-newborn-section mnid-newborn-{tone}',
                    style={'gridColumn': '1 / -1'},
                    children=[
                        html.Div(className='mnid-newborn-section-head', children=[
                            html.Div([
                                html.Div(title, className='mnid-card-title'),
                                html.Div(subtitle, className='mnid-newborn-section-subtitle'),
                            ]),
                            html.Span(tone.upper(), className='mnid-newborn-section-tag'),
                        ]),
                        children,
                    ])


def _first_available_value_counts(df: pd.DataFrame, concepts: list[str], col: str = 'obs_value_coded'):
    for concept in concepts:
        vc = _value_counts(df, concept, col=col)
        if len(vc):
            return vc, concept
    return pd.DataFrame(columns=['label', 'n']), None


def _newborn_tab_content(desc: str, children: list):
    cards = [child for child in children if child is not None]
    if not cards:
        cards = [_no_data_card('No data available for this module.')]
    return html.Div(className='mnid-newborn-tab-panel', children=[
        html.Div(desc, className='mnid-newborn-tab-desc'),
        html.Div(className='mnid-newborn-subgrid mnid-newborn-subgrid-3', children=cards),
    ])

# # MNID main heatmap section layout

def _facilities_requiring_attention(store, year='All years'):
    """Bottom-5 facilities by average MCH coverage - flags needing follow-up."""
    by_fac    = store.get('by_facility', {}).get(year, {})
    fac_x     = by_fac.get('x', [])
    fac_z     = by_fac.get('z', [])
    districts = by_fac.get('districts', [])
    y_targets = store.get('y_targets', [])

    if not fac_x or not fac_z:
        return html.Div()

    rows = []
    for ci, fac in enumerate(fac_x):
        if fac.endswith('*'):   # skip current facility
            continue
        vals = [(fac_z[ri][ci], y_targets[ri] if ri < len(y_targets) else 80)
                for ri in range(len(fac_z))
                if ci < len(fac_z[ri]) and fac_z[ri][ci] is not None]
        if not vals:
            continue
        avg = round(sum(v for v, _ in vals) / len(vals), 1)
        n_critical = sum(1 for v, tgt in vals if v < tgt * 0.85)
        rows.append({
            'fac': fac,
            'fac_name': _FACILITY_NAMES.get(fac, fac),
            'avg': avg,
            'n_critical': n_critical,
            'district': districts[ci] if ci < len(districts) else '',
        })

    if not rows:
        return html.Div()

    rows_sorted = sorted(rows, key=lambda r: r['avg'])[:5]

    hdr_st = {
        'fontSize': '9px', 'fontWeight': '700', 'color': MUTED,
        'padding': '4px 8px', 'borderBottom': f'1.5px solid {BORDER}',
        'textTransform': 'uppercase', 'letterSpacing': '0.06em',
    }
    def _fac_row(r):
        color = _cov_color(r['avg'])
        if r['n_critical'] > 0:
            tag = html.Span(f'{r["n_critical"]} critical', style={
                'background': '#FEF2F2', 'color': DANGER_C,
                'border': '1px solid #FECACA',
                'fontSize': '9px', 'fontWeight': '600',
                'padding': '1px 7px', 'borderRadius': '8px',
            })
        else:
            tag = html.Span('Monitoring', style={
                'background': '#FFFBEB', 'color': '#92400E',
                'border': '1px solid #FDE68A',
                'fontSize': '9px', 'fontWeight': '600',
                'padding': '1px 7px', 'borderRadius': '8px',
            })
        return html.Tr(children=[
            html.Td(r['fac_name'], style={
                'fontSize': '11px', 'fontWeight': '600', 'padding': '7px 8px', 'color': TEXT,
            }),
            html.Td(r['district'], style={'fontSize': '10px', 'color': MUTED, 'padding': '7px 8px'}),
            html.Td(f'{_display_pct(r["avg"]):.0f}%', style={
                'fontSize': '13px', 'fontWeight': '700', 'color': color, 'padding': '7px 8px',
                'textAlign': 'center',
            }),
            html.Td(tag, style={'padding': '7px 8px', 'textAlign': 'left'}),
        ])

    return html.Div(className='mnid-card', style={'marginBottom': '12px'}, children=[
        html.Div('FACILITIES REQUIRING ATTENTION', className='mnid-section-lbl'),
        html.P(
            'Bottom 5 facilities by average coverage across all tracked MCH indicators.',
            style={'fontSize': '10px', 'color': MUTED, 'marginBottom': '8px'},
        ),
        html.Table(className='mnid-priority-tbl', children=[
            html.Thead(html.Tr([
                html.Th('Facility', style=hdr_st),
                html.Th('District', style=hdr_st),
                html.Th('Avg Cov.', style=hdr_st),
                html.Th('Indicators', style=hdr_st),
            ])),
            html.Tbody([_fac_row(r) for r in rows_sorted]),
        ]),
    ])


def _coverage_heatmap_section(
    indicators: list,
    facility_code: str,
    mch_full: pd.DataFrame,
    precomputed_store: dict | None = None,
) -> tuple:
    """Multi-view indicator heatmap with Malawi district panel and live filters."""
    from mnid.layout import _build_district_gauge_row
    tracked = [i for i in indicators if i.get('status') == 'tracked']
    store   = precomputed_store if precomputed_store is not None else _compute_heatmap_store(mch_full, tracked, facility_code)

    district_gauges = _build_district_gauge_row(store)

    dyn_districts = store.get('all_districts', [])
    cur_dist   = store.get('current_district', dyn_districts[0] if dyn_districts else '')
    initial_fig   = _build_heatmap_fig(store, 'by_district', 'All years', cur_dist if cur_dist else None)
    all_labels = store.get('y_labels', [])
    years = ['All years']
    if len(mch_full) and 'Date' in mch_full.columns:
        years.extend(str(y) for y in sorted(mch_full['Date'].dt.year.dropna().astype(int).unique().tolist()))

    year_opts     = [{'label': y, 'value': y} for y in years]
    district_opts = [{'label': 'All districts', 'value': 'All'}] + [{'label': d, 'value': d} for d in dyn_districts]
    ind_opts      = [{'label': lbl, 'value': lbl} for lbl in all_labels]
    default_perf_inds = all_labels[:8] if len(all_labels) >= 8 else all_labels

    _dd_style = {'fontSize': '12px', 'minWidth': '0'}
    _lbl_style = {'fontSize': '10px', 'color': MUTED, 'fontWeight': '600',
                  'marginBottom': '3px'}

    perf_data_districts = [d for d in dyn_districts if d]
    perf_dist_opts = [{'label': d, 'value': d} for d in perf_data_districts]
    perf_default_districts = [cur_dist] if cur_dist and cur_dist in perf_data_districts else None
    heatmap_default_district = cur_dist if cur_dist and cur_dist in dyn_districts else 'All'

    performance_card = html.Div(className='mnid-card mnid-performance-block',
                    style={'marginBottom': '12px'}, children=[
        dcc.Store(id='mnid-heatmap-store', data=store),
        html.Div('FACILITY PERFORMANCE', className='mnid-section-lbl'),
        html.Div(style={'fontSize': '11px', 'color': DIM, 'marginBottom': '10px'},
                 children='Facility-level coverage heatmap. Filter by district, year, or indicators.'),
        html.Div(className='mnid-performance-shell', children=[
            html.Div(id='mnid-performance-aggregate', className='mnid-performance-aggregate',
                     children=_build_district_gauge_row(store, 'All years')),
            html.Div(className='mnid-performance-table-card', children=[
                html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr 1.6fr',
                                'gap': '8px', 'marginBottom': '10px'}, children=[
                    html.Div([
                        html.Div('Districts', style=_lbl_style),
                        dcc.Dropdown(
                            id='mnid-performance-district',
                            options=perf_dist_opts,
                            value=perf_default_districts,
                            multi=True,
                            placeholder='All districts',
                            style=_dd_style,
                        ),
                    ]),
                    html.Div([
                        html.Div('Year', style=_lbl_style),
                        dcc.Dropdown(
                            id='mnid-performance-year',
                            options=year_opts,
                            value='All years',
                            clearable=False,
                            style=_dd_style,
                        ),
                    ]),
                    html.Div([
                        html.Div('Indicators', style=_lbl_style),
                        dcc.Dropdown(
                            id='mnid-performance-indicators',
                            options=ind_opts,
                            value=default_perf_inds,
                            multi=True,
                            placeholder='Select indicators...',
                            style=_dd_style,
                        ),
                    ]),
                ]),
                html.Div(
                    id='mnid-performance-heatmap-table',
                    className='mnid-performance-heatmap-graph',
                    children=_build_facility_performance_heatmap_fig(store, 'All years', perf_default_districts, default_perf_inds, 'All'),
                ),
                html.Div(className='mnid-performance-key', children=[
                    html.Div('Performance Color Scale', className='mnid-performance-key-title'),
                    html.Div(className='mnid-performance-key-row', children=[html.Span('Excellent (>90%)'), html.Div(className='mnid-performance-swatch excellent')]),
                    html.Div(className='mnid-performance-key-row', children=[html.Span('Moderate (60-80%)'), html.Div(className='mnid-performance-swatch moderate')]),
                    html.Div(className='mnid-performance-key-row', children=[html.Span('Poor (<50%)'), html.Div(className='mnid-performance-swatch poor')]),
                ]),
                html.Div(
                    id='mnid-performance-attention',
                    className='mnid-performance-attention',
                    children=_build_performance_attention_table(store, 'All years', perf_default_districts, 'All', default_perf_inds),
                ),
            ]),
        ]),
    ])

    heatmap_card = html.Div(id='mnid-heatmap-inner', className='mnid-card',
                    style={'marginBottom': '12px'}, children=[
        html.Div('MAP COVERAGE VIEW', className='mnid-section-lbl'),

        html.Div(className='mnid-map-controls', children=[
            html.Div(className='mnid-map-scope', children=[
                html.Div('Scope', style=_lbl_style),
                dmc.SegmentedControl(
                    id='mnid-heatmap-view',
                    value='by_district',
                    data=[
                        {'label': 'Districts', 'value': 'by_district'},
                        {'label': 'Facilities', 'value': 'district_facs'},
                    ],
                    size='sm',
                    radius='xl',
                    color='green',
                    fullWidth=True,
                ),
            ]),
            html.Div(className='mnid-map-filter-grid', children=[
                html.Div(id='mnid-heatmap-district-wrap', style={'display': 'none'}, children=[
                    html.Div('District Focus', style=_lbl_style),
                    dcc.Dropdown(
                        id='mnid-heatmap-district',
                        options=district_opts,
                        value=heatmap_default_district,
                        clearable=False,
                        style=_dd_style,
                    ),
                ]),
                html.Div(children=[
                    html.Div('Indicators', style=_lbl_style),
                    dcc.Dropdown(
                        id='mnid-heatmap-indicators',
                        options=ind_opts,
                        value=all_labels[0] if all_labels else None,
                        clearable=True,
                        placeholder='Select indicator...',
                        style=_dd_style,
                    ),
                ]),
            ]),
        ]),

        html.Div(className='mnid-heatmap-grid', children=[
            dcc.Graph(
                id='mnid-heatmap-graph',
                className='mnid-heatmap-map',
                animate=True,
                config={'displayModeBar': True,
                        'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                        'scrollZoom': True,
                        'responsive': True,
                        'doubleClick': 'reset'}
                , figure=initial_fig,
                style={'height': '680px', 'width': '100%', 'minWidth': '0'},
                clear_on_unhover=False,
            ),
            html.Div(
                id='mnid-heatmap-right',
                className='mnid-heatmap-panel',
                children=[],
            ),
        ]),

        html.P(
            'Click the scope toggle to switch between district coverage and facility markers. Choose a district when viewing facilities to keep the map readable.',
            style={'fontSize': '10px', 'color': MUTED, 'marginTop': '8px', 'lineHeight': '1.5'},
        ),
    ])

    return performance_card, heatmap_card

# indicator cards

def _ind_card(ind: dict, df: pd.DataFrame) -> html.Div:
    if ind.get('status') == 'awaiting_baseline':
        return html.Div(className='mnid-ind-card awaiting', children=[
            html.Div(ind['label'], className='mnid-ind-label'),
            html.Div([
                html.Span('-', className='mnid-ind-pct info'),
                html.Span('Awaiting baseline', className='mnid-tag mnid-tag-amber'),
            ], className='mnid-ind-top'),
            html.Div(f'Target {ind["target"]}%', className='mnid-ind-sub'),
        ])

    num, den, pct = _cov(df, ind['numerator_filters'], ind['denominator_filters'])
    target = ind['target']
    cls = _css(pct, target)

    if pct >= target:
        badge = html.Span('On target',    className='mnid-tag mnid-tag-green')
    elif pct >= target * 0.85:
        badge = html.Span('Performing',  className='mnid-tag mnid-tag-blue')
    else:
        badge = html.Span('Needs review', className='mnid-tag mnid-tag-red')

    return html.Div(className=f'mnid-ind-card {cls}', children=[
        html.Div(ind['label'], className='mnid-ind-label'),
        html.Div([
            html.Span(f'{_display_pct(pct):.0f}%', className=f'mnid-ind-pct {cls}'),
            badge,
        ], className='mnid-ind-top'),
        html.Div(f'{num} / {den}  -  Target {target}%', className='mnid-ind-sub'),
    ])


# # MNID phase gauge donuts

def _phase_gauge_fig(avg_pct: float, color: str) -> go.Figure:
    """Mini donut gauge for a single care phase."""
    rest = max(0.0, 100.0 - avg_pct)
    fig = go.Figure(go.Pie(
        values=[avg_pct, rest],
        hole=0.72,
        marker=dict(colors=[color, GRID_C], line=dict(color='#fff', width=0)),
        textinfo='none',
        hoverinfo='skip',
        sort=False,
        direction='clockwise',
        rotation=90,
    ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=4, r=4, t=4, b=4),
        height=100,
        showlegend=False,
        annotations=[dict(
            text=f'<b>{_display_pct(avg_pct):.0f}%</b>',
            x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False,
            font=dict(size=20, color=color, family=FONT),
        )],
    )
    return fig


def _phase_gauge_row(by_cat: dict, df: pd.DataFrame) -> html.Div:
    """Row of 4 mini donut gauges - one per care phase."""
    phases = [
        ('ANC',     'Antenatal Care',    CAT_PALETTES['ANC'][0],     'anc'),
        ('Labour',  'Labour & Delivery', CAT_PALETTES['Labour'][0],  'labour'),
        ('Newborn', 'Newborn Care',       CAT_PALETTES['Newborn'][0], 'newborn'),
        ('PNC',     'Postnatal Care',    CAT_PALETTES['PNC'][0],     'pnc'),
    ]
    cards = []
    for cat_key, cat_label, cat_color, css_cls in phases:
        inds = [i for i in by_cat.get(cat_key, []) if i.get('status') == 'tracked']
        if not inds:
            continue
        computed = [_cov(df, i['numerator_filters'], i['denominator_filters'])
                    for i in inds]
        avg_pct = round(sum(c[2] for c in computed) / len(computed), 1) if computed else 0.0
        on_tgt  = sum(1 for c, i in zip(computed, inds) if c[2] >= i['target'])
        color   = _cov_color(avg_pct)

        fig = _phase_gauge_fig(avg_pct, color)
        cards.append(html.Div(className=f'mnid-phase-gauge {css_cls}', children=[
            html.Div(cat_label, className='mnid-phase-gauge-title'),
            dcc.Graph(figure=fig, config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                      style={'height': '100px'}),
            html.Div(className='mnid-phase-gauge-on', children=[
                html.B(f'{on_tgt}/{len(inds)}'), ' on target',
            ]),
        ]))
    return html.Div(className='mnid-gauge-row', children=cards)


# # MNID key clinical outcomes

def _clinical_donuts_section(df: pd.DataFrame) -> html.Div:
    """Always-visible donut row for key clinical outcomes."""
    donut_specs = [
        ('Place of delivery', 'Place of Delivery', {
            'This facility': OK_C, 'this facility': OK_C,
            'Referral facility': WARN_C, 'Home': DANGER_C,
        }),
        ('Outcome of the delivery', 'Birth Outcome', {
            'Live births': OK_C,
            'Fresh stillbirth': DANGER_C,
            'Macerated stillbirth': '#92400E',
        }),
        ('Breast feeding', 'Breastfeeding Mode', {
            'Exclusive': OK_C, 'Mixed': WARN_C, 'Not breastfeeding': DANGER_C,
        }),
        ('Thermal status on admission', 'Newborn Thermal Status', {
            'Not hypothermic': OK_C,
            'Mild hypothermia': WARN_C,
            'Moderate hypothermia': DANGER_C,
        }),
    ]
    cards = []
    for concept, title, color_map in donut_specs:
        vc  = _value_counts(df, concept)
        fig = _donut(vc, title, color_map=color_map)
        if fig:
            fig.update_layout(height=200, margin=dict(l=4, r=4, t=32, b=28))
            cards.append(html.Div(className='mnid-chart-card', children=[
                dcc.Graph(figure=fig, config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                          style={'height': '200px'}),
            ]))

    if not cards:
        return html.Div()

    return html.Div([
        html.Div('KEY CLINICAL OUTCOMES', className='mnid-section-lbl'),
        html.Div(className='mnid-donut-grid', children=cards),
    ])


# # MNID coverage phase bar chart

def _coverage_phase_fig(
    title: str,
    indicators: list,
    df: pd.DataFrame,
    agg_df=None,
    start_date=None,
    end_date=None,
    facility_codes=None,
    districts=None,
    grain: str = 'monthly',
    row_height: int = 38,
    precomputed: dict | None = None,
) -> go.Figure:
    """Horizontal bar chart: one bar per indicator coloured by status vs target.

    `precomputed`, if given, maps indicator id -> (num, den, pct) so callers
    that already computed coverage (e.g. for an average pill) don't pay for it twice.
    """
    if agg_df is not None:
        from mnid.aggregation.store import query_coverage as _agg_cov
        def _get_cov(ind):
            return _agg_cov(agg_df, ind['id'], start_date, end_date,
                            facility_codes=facility_codes or None,
                            districts=districts or None,
                            grain=grain,
                            indicator_label=ind.get('label'))
    else:
        def _get_cov(ind):
            return _cov(df, ind['numerator_filters'], ind['denominator_filters'])

    rows = []
    for ind in indicators:
        if ind.get('status') == 'awaiting_baseline':
            rows.append({'label': ind['label'][:36], 'pct': None,
                         'target': ind['target'], 'cls': 'await',
                         'sub': 'Awaiting baseline'})
        else:
            if precomputed is not None and ind['id'] in precomputed:
                num, den, pct = precomputed[ind['id']]
            else:
                num, den, pct = _get_cov(ind)
            cls = _css(pct, ind['target'])
            rows.append({'label': ind['label'][:36], 'pct': pct,
                         'target': ind['target'], 'cls': cls,
                         'sub': f'{num}/{den}'})

    if not rows:
        return go.Figure()

    # Reversed so first indicator is at the top
    rows = list(reversed(rows))
    labels  = [r['label']  for r in rows]
    values  = [r['pct'] if r['pct'] is not None else 0 for r in rows]
    targets = [r['target'] for r in rows]
    colors  = [{'ok': OK_C, 'warn': WARN_C, 'danger': DANGER_C}.get(r['cls'], MUTED)
               for r in rows]
    text_vals = [f"{r['pct']:.0f}%" if r['pct'] is not None else 'No data' for r in rows]

    wide = row_height > 38
    height = max(len(rows) * row_height + 70, CHART_HEIGHT_SM)

    fig = go.Figure()

    # Bars
    fig.add_trace(go.Bar(
        x=values, y=labels,
        orientation='h',
        marker=dict(color=colors, opacity=0.88,
                    line=dict(color='rgba(0,0,0,0)')),
        text=text_vals,
        textposition='outside',
        textfont=dict(size=11 if wide else 10, color=TEXT, family=FONT),
        cliponaxis=False,
        hovertemplate='<b>%{y}</b><br>Coverage: %{x:.1f}%<extra></extra>',
        showlegend=False,
    ))

    # Target markers as a scatter overlay
    fig.add_trace(go.Scatter(
        x=targets, y=labels,
        mode='markers',
        marker=dict(symbol='line-ew', size=16 if wide else 14, color='#64748B',
                    line=dict(color='#64748B', width=2)),
        name='Target',
        hovertemplate='Target: %{x:.0f}%<extra></extra>',
    ))

    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        height=height,
        margin=dict(l=8, r=60, t=8, b=8),
        xaxis=dict(range=[0, 115], showgrid=True, gridcolor=GRID_C,
                   zeroline=False, showline=False,
                   ticksuffix='%', tickfont=dict(size=10 if wide else 9, color=MUTED)),
        yaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickfont=dict(size=11 if wide else 10, color=DIM), automargin=True),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        legend=dict(orientation='h', x=0, y=-0.06, xanchor='left',
                    font=dict(size=9, color=DIM)),
        bargap=0.22 if wide else 0.28,
    )
    return fig


def _no_data_card(message: str = 'No data available for this period.') -> html.Div:
    """Inline empty-state card for individual chart sections."""
    return html.Div(className='mnid-chart-card', style={'gridColumn': '1 / -1'}, children=[
        html.Div(style={
            'display': 'flex', 'flexDirection': 'column',
            'alignItems': 'center', 'justifyContent': 'center',
            'padding': '40px 24px', 'gap': '10px',
        }, children=[
            html.Div('-', style={
                'fontSize': '32px', 'color': MUTED, 'lineHeight': '1',
            }),
            html.Div(message, style={
                'fontSize': '13px', 'color': DIM, 'fontFamily': FONT,
                'textAlign': 'center',
            }),
        ]),
    ])


def _coverage_charts_section(
    by_cat: dict,
    df: pd.DataFrame,
    categories: list | None = None,
    agg_df=None,
    start_date=None,
    end_date=None,
    facility_codes=None,
    districts=None,
    grain: str = 'monthly',
) -> html.Div:
    """2-column grid of per-phase coverage bar charts (replaces accordion cards)."""
    if agg_df is not None:
        from mnid.aggregation.store import query_coverage as _agg_cov
        def _compute(ind):
            return _agg_cov(agg_df, ind['id'], start_date, end_date,
                            facility_codes=facility_codes or None,
                            districts=districts or None,
                            grain=grain,
                            indicator_label=ind.get('label'))
    else:
        def _compute(ind):
            return _cov(df, ind['numerator_filters'], ind['denominator_filters'])

    phase_map = {
        'ANC': 'Antenatal Care (ANC)',
        'Labour': 'Labour & Delivery',
        'Newborn': 'Newborn Care',
        'PNC': 'Postnatal Care (PNC)',
    }
    phases = [(cat, phase_map.get(cat, cat)) for cat in _resolve_category_order(
        [{'category': k} for k in by_cat.keys()], categories
    )]
    active_phases = [(c, t) for c, t in phases if by_cat.get(c)]
    single_card = len(active_phases) == 1
    row_height = 52 if single_card else 38

    cards = []
    for cat_key, cat_title in phases:
        inds = by_cat.get(cat_key, [])
        if not inds:
            continue
        tracked  = [i for i in inds if i.get('status') == 'tracked']
        awaiting = [i for i in inds if i.get('status') == 'awaiting_baseline']
        computed = [_compute(i) for i in tracked]
        cov_by_id = {ind['id']: c for ind, c in zip(tracked, computed)}
        avg_pct  = round(sum(c[2] for c in computed) / len(computed), 0) if computed else None

        pills = [html.Span(f'{len(tracked)} available', className='mnid-pill mnid-pill-green')]
        if awaiting:
            pills.append(html.Span(f'{len(awaiting)} awaiting', className='mnid-pill mnid-pill-amber'))
        if avg_pct is not None:
            pc = 'mnid-pill-green' if avg_pct >= 80 else ('mnid-pill-amber' if avg_pct >= 65 else 'mnid-pill-red')
            pills.append(html.Span(f'Avg {_display_pct(avg_pct):.0f}%', className=f'mnid-pill {pc}'))

        fig = _coverage_phase_fig(cat_title, inds, df,
                                   agg_df=agg_df, start_date=start_date, end_date=end_date,
                                   facility_codes=facility_codes, districts=districts, grain=grain,
                                   row_height=row_height, precomputed=cov_by_id)
        inner_height = max(len(inds) * row_height + 70, CHART_HEIGHT_SM)
        outer_height = _clamp_chart_height(inner_height, CHART_HEIGHT_SM, CHART_HEIGHT_LG)

        title_style = {'fontSize': '13px' if single_card else '12px', 'fontWeight': '600', 'color': TEXT}
        cards.append(html.Div(className='mnid-chart-card', children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between',
                            'alignItems': 'center', 'marginBottom': '6px' if single_card else '4px'}, children=[
                html.Div(cat_title, style=title_style),
                html.Div(className='mnid-pills', children=pills),
            ]),
            _graph_scroll_wrap(
                dcc.Graph(
                    figure=fig,
                    config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                    style=_graph_style(inner_height),
                ),
                outer_height,
            ),
            html.P('|= target', style={'fontSize': '9px', 'color': MUTED,
                                        'margin': '2px 0 0', 'textAlign': 'right'}),
        ]))

    if not cards:
        return html.Div(className='mnid-chart-grid',
                        children=[_no_data_card('No indicators configured for this facility.')])
    return html.Div(className='mnid-chart-grid', children=cards)


# accordion helpers (kept for analysis sections)

def _acc_section(sec_id, title, indicators, df, default_open=False):
    tracked  = [i for i in indicators if i.get('status') == 'tracked']
    awaiting = [i for i in indicators if i.get('status') == 'awaiting_baseline']
    computed = [_cov(df, i['numerator_filters'], i['denominator_filters'])
                for i in tracked]
    avg_pct  = round(sum(c[2] for c in computed) / len(computed), 0) if computed else None

    pills = [html.Span(f'{len(tracked)} available', className='mnid-pill mnid-pill-green')]
    if awaiting:
        pills.append(html.Span(f'{len(awaiting)} awaiting',
                               className='mnid-pill mnid-pill-amber'))
    if avg_pct is not None:
        pc = 'mnid-pill-green' if avg_pct >= 80 else ('mnid-pill-amber' if avg_pct >= 65
                                                        else 'mnid-pill-red')
        pills.append(html.Span(f'Avg {_display_pct(avg_pct):.0f}%', className=f'mnid-pill {pc}'))

    return dmc.AccordionItem(value=sec_id, children=[
        dmc.AccordionControl(html.Div(style={
            'display':'flex','alignItems':'center',
            'justifyContent':'space-between','width':'100%','gap':'12px',
        }, children=[
            html.Span(title, style={'fontSize':'13px','fontWeight':'500','color':TEXT}),
            html.Div(className='mnid-pills', children=pills),
        ])),
        dmc.AccordionPanel(
            html.Div(className='mnid-ind-grid',
                     children=[_ind_card(i, df) for i in indicators]),
            pt='sm', pb='md',
        ),
    ])


def _chart_acc_section(sec_id, title, charts):
    """Accordion panel containing chart cards in a responsive 2-col grid."""
    return dmc.AccordionItem(value=sec_id, children=[
        dmc.AccordionControl(
            html.Span(title, style={'fontSize':'13px','fontWeight':'500','color':TEXT})
        ),
        dmc.AccordionPanel(
            html.Div(className='mnid-chart-grid', children=charts),
            pt='sm', pb='md',
        ),
    ])


# themed analysis charts

def _anc_charts(df):
    monthly = _monthly_visits(df, 'ANC VISIT')
    charts = []

    fig = _line(monthly, 'ANC Visits Over Time', color=_TREND_ACCENT['ANC'], y_label='Unique Clients')
    if fig: charts.append(_chart_card('', fig))

    for concept, title in [
        ('Anemia screening',            'Anaemia Screening'),
        ('Infection screening',         'Infection Screening'),
        ('High blood pressure screening','Blood Pressure Screening'),
    ]:
        vc = _value_counts(df, concept)
        fig = _donut(vc, title, color_map={
            'Screened': '#2563EB', 'Not screened': '#94A3B8',
        })
        if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'POCUS completed')
    fig = _donut(vc, 'POCUS Completed', color_map={'Yes': '#0F766E', 'No': '#94A3B8'})
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'HIV Test')
    fig = _donut(vc, 'HIV Testing Status', color_map={
        'Non-reactive': '#2563EB', 'Reactive': '#DB2777',
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Number of tetanus doses', col='Value')
    fig = _hbar(vc, 'Tetanus Dose Distribution')
    if fig: charts.append(_chart_card('', fig))

    return charts


def _labour_charts(df):
    from mnid.layout import _pph_cascade
    charts = []

    cascade = _pph_cascade(df)
    if cascade:
        charts.append(cascade)

    monthly = _monthly_visits(df, 'LABOUR AND DELIVERY')
    fig = _line(monthly, 'Labour & Delivery Visits', color=_TREND_ACCENT['Labour'], y_label='Clients')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Place of delivery')
    fig = _donut(vc, 'Place of Delivery', color_map={
        'This facility': '#2563EB', 'this facility': '#2563EB',
        'Referral facility': '#0F766E', 'Home': '#C2410C', 'In transit': '#64748B',
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Mode of delivery')
    fig = _donut(vc, 'Mode of Delivery')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Obstetric complications')
    fig = _hbar(vc, 'Obstetric Complications')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Outcome of the delivery')
    fig = _donut(vc, 'Birth Outcome', color_map={
        'Live births': '#0F766E',
        'Fresh stillbirth': '#DB2777',
        'Macerated stillbirth': '#7C3AED',
    })
    if fig: charts.append(_chart_card('', fig))

    for concept, label in [
        ('Antenatal corticosteroids given', 'Antenatal Corticosteroids'),
        ('Prophylactic azithromycin given', 'Prophylactic Azithromycin'),
        ('PPH treatment bundle',            'PPH Treatment Bundle'),
        ('Digital intrapartum monitoring',  'Digital Monitoring'),
    ]:
        vc = _value_counts(df, concept)
        fig = _donut(vc, label, color_map={
            'Yes': '#2563EB', 'Used': '#2563EB', 'Completed': '#2563EB',
            'Partial': '#C2410C',
            'No': '#94A3B8', 'Not used': '#94A3B8',
            'Not required': '#CBD5E1', 'Not eligible': '#CBD5E1',
        })
        if fig: charts.append(_chart_card('', fig))

    return charts


def _pnc_charts(df):
    charts = []
    monthly = _monthly_visits(df, 'POSTNATAL CARE')
    fig = _line(monthly, 'PNC Visits Over Time', color=_TREND_ACCENT['PNC'], y_label='Clients')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Postnatal check period')
    fig = _hbar(vc, 'PNC Visit Timing')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Breast feeding')
    fig = _donut(vc, 'Breastfeeding Mode', color_map={
        'Exclusive': '#2563EB', 'exclusive breastfeeding': '#2563EB',
        'Mixed': '#0F766E', 'Not breastfeeding': '#7C3AED',
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Status of the mother')
    fig = _donut(vc, 'Mother Final Status', color_map={
        'Stable': '#2563EB', 'Referred': '#C2410C', 'Death': '#DB2777',
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Status of baby')
    fig = _donut(vc, 'Baby Final Status', color_map={
        'Stable': '#2563EB', 'Referred': '#C2410C', 'Died': '#DB2777',
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Postnatal complications')
    fig = _hbar(vc, 'Postnatal Complications')
    if fig: charts.append(_chart_card('', fig))

    return charts


def _newborn_charts(df):
    monthly = _monthly_visits(df, 'NEONATAL CARE')
    fig = _line(monthly, 'Neonatal Care Admissions', color=_TREND_ACCENT['Newborn'], y_label='Babies')
    admission_card = _chart_card('', fig) if fig else None

    thermal_num, thermal_den, thermal_pct = _concept_rate(df, 'Thermal status on admission', ['Not hypothermic'])
    resus_num, resus_den, resus_pct = _concept_rate(df, 'Neonatal resuscitation provided', ['Yes', 'Stimulation only', 'Bag and mask'])
    kmc_num, kmc_den, kmc_pct = _concept_rate(df, 'iKMC initiated', ['Yes'])
    support_num, support_den, support_pct = _concept_rate(df, 'CPAP support', ['Bubble CPAP', 'Nasal oxygen'])

    summary_cards = [
        _newborn_summary_card('Thermal Stability', thermal_num, thermal_den, thermal_pct, '#0F766E',
                              'Babies arriving normothermic'),
        _newborn_summary_card('Resuscitation Response', resus_num, resus_den, resus_pct, '#2563EB',
                              'Babies receiving any resuscitation action'),
        _newborn_summary_card('iKMC Initiation', kmc_num, kmc_den, kmc_pct, '#7C3AED',
                              'Eligible babies initiated on KMC'),
        _newborn_summary_card('Respiratory Support', support_num, support_den, support_pct, '#0891B2',
                              'Bubble CPAP or nasal oxygen recorded'),
    ]
    overview_card = html.Div(className='mnid-chart-card', children=[
        html.Div(className='mnid-newborn-metric-grid', children=summary_cards)
    ])

    run_specs = [
        ('Thermal status on admission', ['Not hypothermic'], 'Thermal Stability', 85, '#0F766E'),
        ('Neonatal resuscitation provided', ['Yes', 'Stimulation only', 'Bag and mask'], 'Resuscitation Response', 80, '#2563EB'),
        ('iKMC initiated', ['Yes'], 'iKMC Initiation', 75, '#7C3AED'),
        ('Phototherapy given', ['Yes'], 'Phototherapy Use', 70, '#C2410C'),
        ('Parenteral antibiotics given', ['Yes'], 'Antibiotics Given', 85, '#DB2777'),
        ('CPAP support', ['Bubble CPAP'], 'Bubble CPAP Use', 60, '#0891B2'),
    ]
    run_cards = {}
    for concept, values, title, target, color in run_specs:
        run_fig = _monthly_concept_rate(df, concept, positive_values=values, title=title, target=target, color=color)
        if run_fig:
            run_cards[title] = html.Div(className='mnid-chart-card', children=[
                dcc.Graph(
                    figure=run_fig,
                    config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                    style={'height': '210px'},
                ),
            ])

    mix_fig = _monthly_concept_mix_fig(
        df,
        'Thermal status on admission',
        [
            ('Not hypothermic', ['Not hypothermic'], '#2563EB'),
            ('Mild hypothermia', ['Mild hypothermia'], '#0F766E'),
            ('Moderate/Severe', ['Moderate hypothermia', 'Severe hypothermia'], '#DB2777'),
        ],
        'Thermal Status Mix Over Time',
    )
    thermal_mix_card = _chart_card('', mix_fig) if mix_fig else None

    resp_mix_fig = _monthly_concept_mix_fig(
        df,
        'CPAP support',
        [
            ('Bubble CPAP', ['Bubble CPAP'], '#7C3AED'),
            ('Nasal oxygen', ['Nasal oxygen'], '#0891B2'),
            ('No advanced support', ['None', 'No'], '#CBD5E1'),
        ],
        'Respiratory Support Mix Over Time',
    )
    respiratory_mix_card = _chart_card('', resp_mix_fig) if resp_mix_fig else None

    vc = _value_counts(df, 'Thermal status on admission')
    fig = _donut(vc, 'Thermal Status on Admission', color_map={
        'Not hypothermic': '#2563EB',
        'Mild hypothermia': '#0F766E',
        'Moderate hypothermia': '#C2410C',
        'Severe hypothermia': '#DB2777',
    })
    thermal_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'Neonatal resuscitation provided')
    fig = _donut(vc, 'Neonatal Resuscitation', color_map={
        'Yes': '#2563EB', 'Stimulation only': '#0F766E',
        'Bag and mask': '#7C3AED', 'No': '#94A3B8', 'Not required': '#CBD5E1',
    })
    resuscitation_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'iKMC initiated')
    fig = _donut(vc, 'iKMC Initiated', color_map={
        'Yes': '#2563EB', 'No': '#94A3B8', 'Not eligible': '#CBD5E1',
    })
    kmc_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'CPAP support')
    fig = _donut(vc, 'CPAP Support Type', color_map={
        'Bubble CPAP': '#2563EB', 'Nasal oxygen': '#0F766E', 'None': '#94A3B8',
    })
    cpap_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'Phototherapy given')
    fig = _donut(vc, 'Phototherapy Given', color_map={
        'Yes': '#2563EB', 'No': '#94A3B8',
    })
    phototherapy_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'Parenteral antibiotics given')
    fig = _donut(vc, 'Parenteral Antibiotics', color_map={
        'Yes': '#2563EB', 'No': '#94A3B8',
    })
    antibiotics_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'Newborn baby complications')
    fig = _hbar(vc, 'Newborn Complications')
    complications_bar = _chart_card('', fig) if fig else None

    birthweight_vc, birthweight_concept = _first_available_value_counts(
        df,
        ['Birthweight category', 'Birth weight category', 'Birthweight', 'Birth weight'],
        col='obs_value_coded',
    )
    birthweight_chart = None
    if len(birthweight_vc):
        birthweight_fig = _hbar(birthweight_vc, 'Birthweight Distribution', color='#7C3AED')
        if birthweight_fig:
            birthweight_chart = _chart_card('', birthweight_fig)

    mortality_vc, mortality_concept = _first_available_value_counts(
        df,
        ['Status of baby', 'Baby Final Status', 'Outcome of the delivery'],
        col='obs_value_coded',
    )
    mortality_chart = None
    if len(mortality_vc):
        mortality_fig = _donut(mortality_vc, 'Outcome Status', color_map={
            'Stable': '#2563EB', 'Alive': '#2563EB', 'Live births': '#2563EB',
            'Referred': '#C2410C', 'Died': '#DB2777', 'Death': '#DB2777',
            'Fresh stillbirth': '#DB2777', 'Macerated stillbirth': '#7C3AED',
        })
        if mortality_fig:
            mortality_chart = _chart_card('', mortality_fig)

    diagnosis_chart = complications_bar
    quality_cards = [card for card in [phototherapy_donut, antibiotics_donut, thermal_donut] if card is not None]

    tab_specs = [
        ('Admissions', 'Admissions volume and core neonatal service activity.', [overview_card, admission_card]),
        ('Mortality', 'Outcome trends and mortality-related newborn status views.', [mortality_chart]),
        ('Birthweight', 'Birthweight-related distribution views for neonatal review.', [birthweight_chart]),
        ('Thermal Care', 'Thermal stability monitoring and thermal status composition.', [run_cards.get('Thermal Stability'), thermal_mix_card, thermal_donut]),
        ('Respiratory Support', 'Respiratory support and resuscitation monitoring.', [run_cards.get('Resuscitation Response'), run_cards.get('Bubble CPAP Use'), respiratory_mix_card, resuscitation_donut, cpap_donut]),
        ('KMC', 'KMC uptake and related newborn care monitoring.', [run_cards.get('iKMC Initiation'), kmc_donut]),
        ('Infections', 'Infection-related treatment and complication monitoring.', [run_cards.get('Antibiotics Given'), antibiotics_donut, diagnosis_chart]),
        ('Quality of Care', 'Selected intervention and support measures used to review care delivery.', quality_cards),
    ]
    tabs = []
    for label, desc, cards in tab_specs:
        usable_cards = [card for card in cards if card is not None]
        if usable_cards:
            tabs.append((label, desc, usable_cards))

    return [html.Div(className='mnid-chart-card mnid-newborn-workspace', style={'gridColumn': '1 / -1'}, children=[
        html.Div('NEONATAL CLINICAL MODULES', className='mnid-card-title'),
        html.Div('Select a module to view the relevant neonatal charts and indicators.',
                 className='mnid-newborn-section-subtitle', style={'marginBottom': '12px'}),
        dcc.Tabs(
            value=(tabs[0][0] if tabs else 'Admissions'),
            className='mnid-newborn-tabs',
            children=[
                dcc.Tab(
                    label=label,
                    value=label,
                    className='mnid-newborn-tab',
                    selected_className='mnid-newborn-tab--selected',
                    children=_newborn_tab_content(desc, cards),
                )
                for label, desc, cards in tabs
            ],
        ),
    ])]


# system readiness

def _stat_row(label, num, den, pct, tgt=None):
    cls = _css(pct, tgt) if tgt else 'info'
    status_map = {'ok': 'On target', 'warn': 'Watch', 'danger': 'Needs action', 'info': 'Monitor'}
    return html.Div(className=f'mnid-stat-row {cls}', children=[
        html.Span(label, className='mnid-stat-lbl'),
        html.Div(style={'display':'flex','gap':'8px','alignItems':'center', 'flexWrap': 'wrap', 'justifyContent': 'flex-end'}, children=[
            html.Span(f'{num}/{den}', className=f'mnid-stat-meta {cls}'),
            html.Span(f'{_display_pct(pct):.0f}%', className=f'mnid-stat-val {cls}'),
            html.Span(status_map.get(cls, 'Monitor'), className=f'mnid-stat-tag {cls}'),
        ]),
    ])


def _system_readiness(df, supply_inds, wf_inds, dq_inds):
    if not (supply_inds or wf_inds or dq_inds):
        return html.Div()

    def _rows(inds, tgt_key='target_pct'):
        rows = []
        for ind in inds:
            num, den, pct = _cov(df, ind['numerator_filters'], ind['denominator_filters'])
            rows.append(_stat_row(ind['label'], num, den, pct, ind.get(tgt_key)))
        return rows

    section_specs = [
        (
            'Equipment & Supplies',
            'Supply-side indicators covering medicines, devices, and essential equipment.',
            _rows(supply_inds),
        ),
        (
            'Workforce Competency',
            'Live competency and staffing readiness indicators from the current MNID scope.',
            _rows(wf_inds),
        ),
        (
            'Data Quality',
            'Completeness and timeliness signals supporting dashboard confidence.',
            _rows(dq_inds, 'target_pct'),
        ),
    ]

    cards = []
    for title, subtitle, rows in section_specs:
        cards.append(
            dmc.Paper(
                withBorder=True,
                radius='md',
                p='md',
                shadow='xs',
                style={'borderColor': '#e2e8f0', 'height': '100%'},
                children=[
                    html.Div(title, style={'fontSize': '13px', 'fontWeight': '700', 'color': '#0f172a', 'marginBottom': '4px'}),
                    html.Div(subtitle, style={'fontSize': '11px', 'color': '#64748b', 'lineHeight': '1.45', 'marginBottom': '12px'}),
                    *(rows or [html.Div(
                        'No live observations in the current selection.',
                        style={
                            'fontSize': '11px',
                            'color': '#94a3b8',
                            'border': '1px dashed #cbd5e1',
                            'borderRadius': '10px',
                            'padding': '12px 14px',
                            'background': '#f8fafc',
                        },
                    )]),
                ],
            )
        )

    return dmc.SimpleGrid(cols=3, spacing='lg', mb='lg', children=cards)


def _compare_status_counts(df: pd.DataFrame, tracked: list) -> dict:
    """Counts indicators by status for a given filtered dataframe."""
    on_tgt = 0
    below  = 0
    no_dat = 0
    for ind in tracked:
        num, den, pct = _cov(df, ind['numerator_filters'], ind['denominator_filters'])
        if den <= 0:
            no_dat += 1
        else:
            if pct >= ind.get('target', 0):
                on_tgt += 1
            else:
                below += 1
    return {'On target': on_tgt, 'Below target': below, 'No data': no_dat}


def _validate_indicator_configs(indicators: list) -> list:
    """Return only indicators with required keys."""
    required = {'id', 'label', 'target', 'numerator_filters', 'denominator_filters'}
    return [i for i in indicators if required.issubset(i.keys())]


def _build_compare_pie(title: str, counts: dict) -> go.Figure:
    labels = list(counts.keys())
    values = list(counts.values())
    colors = ['#2563EB', '#0F766E', '#D6D3CB']

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.35,
        marker=dict(colors=colors, line=dict(color='#fff', width=1)),
        textinfo='percent',
        hovertemplate='<b>%{label}</b><br>%{value} indicators (%{percent})<extra></extra>',
    ))
    fig.update_layout(**_CHART_LAYOUT)
    fig.update_layout(
        title=dict(text=title,
                   font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.98),
        height=260,
        margin=dict(l=10, r=10, t=36, b=10),
        legend=dict(orientation='h', x=0, y=-0.08, xanchor='left',
                    font=dict(size=9, color=DIM)),
    )
    return fig


def _build_compare_bar(title: str, counts: dict) -> go.Figure:
    labels = list(counts.keys())
    values = list(counts.values())
    colors = ['#2563EB', '#0F766E', '#D6D3CB']

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation='h',
        marker=dict(color=colors, line=dict(color='#fff', width=1)),
        text=[str(v) for v in values],
        textposition='auto',
        hovertemplate='<b>%{y}</b>: %{x} indicators<extra></extra>',
    ))
    fig.update_layout(**_CHART_LAYOUT)
    fig.update_layout(
        title=dict(text=title,
                   font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.98),
        height=260,
        margin=dict(l=10, r=100, t=36, b=10),
        xaxis=dict(title='Indicators', showgrid=True, gridcolor=GRID_C),
        yaxis=dict(showgrid=False),
    )
    return fig


def _build_compare_heatmap(title: str, df: 'pd.DataFrame', tracked: list) -> go.Figure:
    """Single-entity heatmap: one row per indicator showing coverage %."""
    names, pcts, colors_list = [], [], []
    heat_palette = ['#DBEAFE', '#93C5FD', '#60A5FA', '#2563EB', '#1D4ED8']
    for ind in tracked:
        label = ind.get('label', ind.get('id', '-'))
        if df.empty:
            pct = 0.0
        else:
            _, _, pct = _cov(df, ind['numerator_filters'], ind['denominator_filters'])
        names.append(label[:38])
        pcts.append(_display_pct(pct))
        if pct == 0:
            colors_list.append('#E5E7EB')
        else:
            bucket = min(int((_display_pct(pct) or 0) // 20), len(heat_palette) - 1)
            colors_list.append(heat_palette[bucket])

    if not names:
        fig = go.Figure()
        fig.update_layout(**_CHART_LAYOUT, height=CHART_HEIGHT_MD)
        return fig

    fig = go.Figure(go.Bar(
        x=pcts,
        y=names,
        orientation='h',
        marker=dict(color=colors_list, line=dict(color='#fff', width=0.5)),
        text=[f'{_display_pct(p):.0f}%' for p in pcts],
        textposition='auto',
        hovertemplate='<b>%{y}</b><br>Coverage: %{x:.1f}%<extra></extra>',
    ))
    fig.update_layout(**_CHART_LAYOUT)
    fig.update_layout(
        title=dict(text=title,
                   font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.98),
        height=_clamp_chart_height(max(CHART_HEIGHT_MD, len(names) * 24 + 60), CHART_HEIGHT_MD, CHART_HEIGHT_LG),
        margin=dict(l=10, r=20, t=36, b=10),
        xaxis=dict(title='Coverage %', range=[0, 100], showgrid=True, gridcolor=GRID_C),
        yaxis=dict(showgrid=False, autorange='reversed'),
    )
    return fig


# comparative analysis section

def _comparative_analysis_section(indicators: list, facility_code: str,
                                  mch_full: pd.DataFrame,
                                  payload_key: str | None = None) -> html.Div:
    """Time-aware comparison across selected facilities or districts and indicators."""
    tracked = [i for i in indicators if i.get('status') == 'tracked']
    all_facs  = sorted(mch_full['Facility_CODE'].dropna().astype(str).unique().tolist()) if len(mch_full) and 'Facility_CODE' in mch_full.columns else sorted(_ALL_FACILITIES[:])
    all_dists = sorted(mch_full['District'].dropna().astype(str).unique().tolist()) if len(mch_full) and 'District' in mch_full.columns else sorted(_ALL_DISTRICTS[:])
    current_dist = _FACILITY_DISTRICT.get(facility_code, '')
    fac_opts = [{'label': _FACILITY_NAMES.get(f, f), 'value': f} for f in all_facs]
    dist_opts = [{'label': d, 'value': d} for d in all_dists]
    ind_opts = [{'label': ind['label'], 'value': ind['id']} for ind in tracked]
    default_facs = ([facility_code] if facility_code in all_facs else all_facs[:2]) or []
    default_dists = ([current_dist] if current_dist in all_dists else all_dists[:2]) or []
    default_inds = [ind['id'] for ind in tracked[:2]]
    try:
        compare_dates = pd.to_datetime(mch_full['Date'], errors='coerce').dropna() if 'Date' in mch_full.columns else pd.Series([], dtype='datetime64[ns]')
        compare_date_min = compare_dates.min().isoformat() if len(compare_dates) else None
        compare_date_max = compare_dates.max().isoformat() if len(compare_dates) else None
    except Exception:
        compare_date_min = compare_date_max = None
    _lbl_style = {
        'fontSize': '11px', 'fontWeight': '600', 'color': '#94A3B8',
        'textTransform': 'uppercase', 'letterSpacing': '0.05em',
        'marginBottom': '5px', 'display': 'block',
    }

    compare_card = html.Div(className='mnid-chart-card mnid-compare-card', children=[
        # -- Header row -----------------------------------------------------------
        html.Div(className='mnid-compare-header', style={'display': 'flex', 'alignItems': 'center',
                        'justifyContent': 'space-between',
                        'marginBottom': '16px', 'flexWrap': 'wrap', 'gap': '10px'}, children=[
            html.Div('COMPARISON ANALYSIS', className='mnid-card-title',
                     style={'marginBottom': '0'}),
            html.Div(className='mnid-compare-mode', style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'flexWrap': 'wrap'}, children=[
                html.Span('Compare by:', style={'fontSize': '11px', 'color': '#94A3B8',
                                                'fontWeight': '600', 'letterSpacing': '0.04em'}),
                dcc.RadioItems(
                    id='mnid-compare-mode',
                    options=[
                        {'label': 'Facility', 'value': 'facility'},
                        {'label': 'District', 'value': 'district'},
                    ],
                    value='facility',
                    inline=True,
                    inputStyle={'marginRight': '5px'},
                    labelStyle={'marginRight': '16px', 'fontSize': '12px',
                                'color': '#E2E8F0', 'cursor': 'pointer', 'fontWeight': '600'},
                ),
                html.Button(
                    id='mnid-compare-chart-toggle',
                    className='mnid-trend-toggle is-line',
                    n_clicks=0,
                    type='button',
                    children=[
                        html.Span('Line', id='mnid-compare-chart-toggle-text', className='mnid-trend-toggle-text'),
                        html.Span(className='mnid-trend-toggle-thumb'),
                    ],
                ),
            ]),
        ]),
        html.Div(className='mnid-compare-filters', style={'display': 'grid', 'gridTemplateColumns': '1.4fr 0.8fr 1.2fr', 'gap': '12px', 'marginBottom': '14px'}, children=[
            html.Div(children=[
                html.Label('Locations', style=_lbl_style),
                dcc.Dropdown(
                    id='mnid-compare-entities',
                    options=fac_opts,
                    value=default_facs,
                    multi=True,
                    placeholder='Select up to 2 locations...',
                ),
            ]),
            html.Div(children=[
                html.Label('Time Grain', style=_lbl_style),
                dcc.Dropdown(
                    id='mnid-compare-time-grain',
                    options=[
                        {'label': 'Daily', 'value': 'daily'},
                        {'label': 'Weekly', 'value': 'weekly'},
                        {'label': 'Monthly', 'value': 'monthly'},
                        {'label': 'Quarterly', 'value': 'quarterly'},
                        {'label': 'Yearly', 'value': 'yearly'},
                    ],
                    value='weekly',
                    clearable=False,
                ),
            ]),
            html.Div(children=[
                html.Label('Indicators', style=_lbl_style),
                dcc.Dropdown(
                    id='mnid-compare-indicators',
                    options=ind_opts,
                    value=default_inds,
                    multi=True,
                    placeholder='Select up to 2 indicators...',
                ),
            ]),
        ]),
        # -- Grouped bar chart ----------------------------------------------------
        dcc.Graph(
            id='mnid-compare-bar-chart',
            config={
                'displayModeBar': 'hover',
                'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'],
                'toImageButtonOptions': {'format': 'png', 'scale': 2},
            },
            className='mnid-compare-chart',
            style={'height': '420px'},
        ),
    ])

    return html.Div(id='mnid-comparative', children=[
        dcc.Store(id='mnid-compare-store', data={
            'tracked':    tracked,
            'data_key':   _remember_ui_payload('compare', mch_full, stable_key=payload_key),
            'facility_options': fac_opts,
            'district_options': dist_opts,
            'current_fac': facility_code,
            'current_dist': current_dist,
            'date_min': compare_date_min,
            'date_max': compare_date_max,
        }),
        dcc.Store(id='mnid-compare-chart-type-store', data='line'),
        html.Div(className='mnid-chart-grid', children=[compare_card]),
    ])
