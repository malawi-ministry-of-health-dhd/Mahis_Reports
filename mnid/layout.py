"""
MNID dashboard layout components.

Contains the topbar, sidebar, alert banner, KPI row, hero donut cards,
priority indicators table, district gauge row, PPH cascade funnel,
and the section anchor helper.
"""
import pandas as pd
import plotly.graph_objects as go
import logging
from dash import html, dcc

from mnid.constants import (
    OK_C, WARN_C, DANGER_C, INFO_C, MUTED, GRID_C, BG, BORDER, TEXT, DIM, FONT,
    CAT_PALETTES,
    FACILITY_DISTRICT as _FACILITY_DISTRICT,
    FACILITY_NAMES as _FACILITY_NAMES,
)
from mnid.chart_helpers import (
    _CHART_LAYOUT, _CAT_LABELS,
    _css, _display_pct, _target_attainment_pct, _target_mode, _is_inverse_indicator,
    CHART_HEIGHT_MD, CHART_HEIGHT_LG, _clamp_chart_height, _graph_style, _graph_scroll_wrap,
)
from mnid.heatmap import _cov_color

_LOGGER = logging.getLogger(__name__)


# # MNID table header style
_TH = {
    'fontSize': '10px', 'fontWeight': '700', 'color': MUTED,
    'textTransform': 'uppercase', 'letterSpacing': '0.06em',
    'padding': '8px 10px', 'borderBottom': f'2px solid #E2E8F0',
    'textAlign': 'left', 'whiteSpace': 'nowrap',
    'background': '#FAFAFA',
}


# # MNID hero indicator donut row

def _hero_donut_card(label, pct, target, color, mode='max', delta_pct=None,
                     numerator=None, denominator=None):
    """Large CSS conic-gradient donut card with period delta and num/den counts."""
    p = max(0.0, min(float(pct), 100.0))
    r_v = int(color[1:3], 16)
    g_v = int(color[3:5], 16)
    b_v = int(color[5:7], 16)
    cls = _css(p, target, mode)
    badge_map = {
        'ok':     ('#F0FDF4', '#14532D', '#BBF7D0', '✓ On target', color),
        'warn':   ('#FFFBEB', '#92400E', '#FDE68A', '~ Watch',     '#F59E0B'),
        'danger': ('#FEF2F2', '#7F1D1D', '#FECACA', '✕ Review',   '#EF4444'),
    }
    bg, fg, border, txt, stripe_color = badge_map.get(cls, badge_map['danger'])

    if delta_pct is not None:
        if delta_pct > 0.5:
            d_cls, d_arrow = 'mnid-hero-delta-up', '▲'
        elif delta_pct < -0.5:
            d_cls, d_arrow = 'mnid-hero-delta-down', '▼'
        else:
            d_cls, d_arrow = 'mnid-hero-delta-flat', '→'
        d_sign = '+' if delta_pct > 0 else ''
        delta_badge = html.Span(
            f'{d_arrow} {d_sign}{delta_pct:.1f}pp vs prior',
            className=f'mnid-hero-delta {d_cls}',
        )
    else:
        delta_badge = None

    return html.Div(className='mnid-hero-card', style={'position': 'relative', 'overflow': 'hidden'}, children=[
        html.Div(style={
            'position': 'absolute', 'top': '0', 'left': '0', 'right': '0',
            'height': '4px', 'background': stripe_color, 'borderRadius': '16px 16px 0 0',
        }),
        html.Div(style={
            '--mnid-p': f'{p:.1f}',
            'width': '118px', 'height': '118px', 'borderRadius': '50%',
            'background': f'conic-gradient({color} calc(var(--mnid-p) * 1%), {GRID_C} 0)',
            'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
            'margin': '14px auto 10px',
            'animation': 'mnid-donut-in 1.1s cubic-bezier(.34,1.2,.64,1) both',
            'filter': (
                'drop-shadow(0 4px 14px rgba(226,232,240,0.5))'
                if p == 0
                else f'drop-shadow(0 4px 14px rgba({r_v},{g_v},{b_v},0.25))'
            ),
        }, children=[
            html.Div(style={
                'width': '82px', 'height': '82px', 'borderRadius': '50%',
                'background': '#fff',
                'display': 'flex', 'flexDirection': 'column',
                'alignItems': 'center', 'justifyContent': 'center', 'gap': '1px',
            }, children=[
                html.Span(f'{_display_pct(p):.0f}%', style={
                    'fontSize': '23px', 'fontWeight': '800',
                    'color': color, 'lineHeight': '1',
                }),
                html.Span(f'Target {target}%', style={
                    'fontSize': '7.5px', 'color': MUTED,
                    'lineHeight': '1.2', 'marginTop': '2px',
                }),
            ]),
        ]),
        html.Div(label, className='mnid-hero-label'),
        html.Span(txt, style={
            'background': bg, 'color': fg, 'border': f'1px solid {border}',
            'fontSize': '9px', 'fontWeight': '600',
            'padding': '2px 8px', 'borderRadius': '10px',
            'display': 'inline-block', 'marginTop': '6px',
        }),
        delta_badge,
    ])


def _hero_donut_row(computed, preferred_cat: str = 'ANC', section_title: str | None = None):
    """Row of large hero donut cards favouring the requested category first."""
    preferred = [c for c in computed if c.get('category') == preferred_cat]
    heroes = preferred[:5] if preferred else computed[:5]
    if not heroes:
        return html.Div()

    if not section_title:
        label = _CAT_LABELS.get(preferred_cat, str(preferred_cat or 'Program'))
        section_title = f'KEY {label.upper()} INDICATORS'

    cards = []
    for ind in heroes:
        attained = _target_attainment_pct(ind['pct'], ind['target'], ind)
        color = _cov_color(attained)
        cards.append(_hero_donut_card(
            ind['label'], ind['pct'], ind['target'], color, ind,
            delta_pct=ind.get('delta_pct'),
            numerator=ind.get('numerator'),
            denominator=ind.get('denominator'),
        ))

    return html.Div(style={'marginBottom': '12px'}, children=[
        html.Div(section_title, className='mnid-section-lbl'),
        html.Div(className='mnid-hero-row', children=cards),
    ])


# # MNID priority indicators status table

def _priority_table(computed):
    """Priority Indicators Status table with progress bars and status badges."""
    if not computed:
        return html.Div()

    sorted_c = sorted(
        computed,
        key=lambda x: (
            {'danger': 0, 'warn': 1, 'ok': 2}.get(_css(x['pct'], x['target'], x), 0),
            -x.get('attained_pct', _target_attainment_pct(x['pct'], x['target'], x)),
        ),
    )

    def _badge(cls):
        conf = {
            'ok':     ('#F0FDF4', '#14532D', '#BBF7D0', 'On target'),
            'warn':   ('#FFFBEB', '#92400E', '#FDE68A', 'Performing'),
            'danger': ('#FEF2F2', '#7F1D1D', '#FECACA', 'Needs review'),
        }.get(cls, ('#FEF2F2', '#7F1D1D', '#FECACA', 'Needs review'))
        bg, fg, bdr, lbl = conf
        return html.Span(lbl, style={
            'background': bg, 'color': fg, 'border': f'1px solid {bdr}',
            'fontSize': '9px', 'fontWeight': '600',
            'padding': '2px 8px', 'borderRadius': '10px', 'whiteSpace': 'nowrap',
        })

    def _prog(pct, target, mode='max'):
        fill = min(_target_attainment_pct(pct, target, mode), 100)
        col  = {'ok': OK_C, 'warn': WARN_C, 'danger': DANGER_C}.get(_css(pct, target, mode), MUTED)
        return html.Div(style={
            'position': 'relative', 'height': '6px',
            'background': GRID_C, 'borderRadius': '3px', 'minWidth': '90px',
        }, children=[
            html.Div(style={
                'width': f'{fill:.0f}%', 'height': '100%',
                'background': col, 'borderRadius': '3px',
                'transition': 'width 0.4s ease',
            }),
            html.Div(style={
                'position': 'absolute', 'top': '-3px',
                'left': f'{min(100 if _target_mode(mode) == "min" else target, 100)}%',
                'height': '12px', 'width': '1.5px',
                'background': '#94A3B8', 'transform': 'translateX(-50%)',
                'borderRadius': '1px',
            }),
        ])

    cat_dot = {
        'ANC':     CAT_PALETTES['ANC'][0],
        'Labour':  CAT_PALETTES['Labour'][0],
        'Newborn': CAT_PALETTES['Newborn'][0],
        'PNC':     CAT_PALETTES['PNC'][0],
    }

    rows = []
    for ind in sorted_c:
        cls = _css(ind['pct'], ind['target'], ind)
        val_col = {'ok': OK_C, 'warn': WARN_C, 'danger': DANGER_C}.get(cls, TEXT)
        dot_col = cat_dot.get(ind.get('category', ''), MUTED)
        rows.append(html.Tr(style={'borderBottom': f'1px solid {GRID_C}'}, children=[
            html.Td(style={'padding': '8px 10px'}, children=[
                html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '8px'},
                         children=[
                    html.Div(style={'width': '7px', 'height': '7px', 'borderRadius': '50%',
                                    'background': dot_col, 'flexShrink': '0'}),
                    html.Span(ind['label'], style={'fontSize': '11px', 'color': DIM,
                                                   'lineHeight': '1.3'}),
                ]),
            ]),
            html.Td(f"{ind['pct']:.0f}%", style={
                'fontSize': '14px', 'fontWeight': '700', 'color': val_col,
                'padding': '8px 10px', 'textAlign': 'center',
            }),
            html.Td(f'{"<=" if _is_inverse_indicator(ind) else ""}{ind["target"]}%', style={
                'fontSize': '11px', 'color': MUTED,
                'padding': '8px 10px', 'textAlign': 'center',
            }),
            html.Td(_prog(ind['pct'], ind['target'], ind),
                    style={'padding': '8px 10px', 'minWidth': '100px'}),
            html.Td(_badge(cls), style={'padding': '8px 10px'}),
        ]))

    return html.Div(className='mnid-card', style={'marginBottom': '14px'}, children=[
        html.Div('PRIORITY INDICATORS STATUS', className='mnid-section-lbl'),
        html.Div(style={'overflowX': 'auto'}, children=[
            html.Table(className='mnid-priority-tbl', children=[
                html.Thead(html.Tr([
                    html.Th('Indicator Name', style=_TH),
                    html.Th('Coverage',       style={**_TH, 'textAlign': 'center'}),
                    html.Th('Target',         style={**_TH, 'textAlign': 'center'}),
                    html.Th('Progress',       style={**_TH, 'minWidth': '100px'}),
                    html.Th('Status',         style=_TH),
                ])),
                html.Tbody(rows),
            ]),
        ]),
    ])


# # MNID district speedometer gauges

def _district_gauge_fig(pct, district):
    """Plotly Indicator speedometer gauge for a single district."""
    val   = _display_pct(pct) if pct is not None else 0
    color = _cov_color(pct) if pct is not None else MUTED
    fig   = go.Figure(go.Indicator(
        mode  = 'gauge+number',
        value = val,
        number = dict(suffix='%', font=dict(size=30, color=color, family=FONT)),
        title  = dict(text=f'<b>{district}</b>',
                      font=dict(size=13, color=TEXT, family=FONT)),
        gauge  = dict(
            axis=dict(range=[0, 100], tickwidth=1, tickcolor=BORDER,
                      tickfont=dict(size=9, color=MUTED), dtick=25),
            bar=dict(color=color, thickness=0.28),
            bgcolor=GRID_C,
            borderwidth=0,
            steps=[
                dict(range=[0,   40],  color='#FEF2F2'),
                dict(range=[40,  65],  color='#FFFBEB'),
                dict(range=[65,  88],  color='#F0FDF4'),
                dict(range=[88, 100],  color='#DCFCE7'),
            ],
            threshold=dict(
                line=dict(color='#64748B', width=2),
                thickness=0.75, value=80,
            ),
        ),
    ))
    fig.update_layout(
        paper_bgcolor=BG,
        font=dict(family=FONT),
        height=200,
        margin=dict(l=16, r=16, t=52, b=8),
    )
    return fig


def _build_district_gauge_row(store, year='All years'):
    """District performance overview: speedometers for <=5 districts, bar chart for >5."""
    avgs      = store.get('district_avgs', {}).get(year, {})
    districts = store.get('all_districts', [])
    data      = [(d, avgs[d]) for d in districts if avgs.get(d) is not None]
    if not data:
        return html.Div()

    def _status_text(pct):
        if pct >= 80:  return 'Strong performance'
        if pct >= 65:  return 'Moderate coverage'
        return 'Needs attention'

    if len(data) <= 5:
        cards = []
        for dist, pct in data:
            color = _cov_color(pct)
            fig   = _district_gauge_fig(pct, dist)
            cards.append(html.Div(className='mnid-district-gauge-card', children=[
                dcc.Graph(figure=fig,
                          config={'displayModeBar': 'hover',
                                  'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                                  'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                          style={'height': '200px'}),
                html.Div(_status_text(pct), style={
                    'fontSize': '10px', 'color': color,
                    'fontWeight': '600', 'marginTop': '-6px', 'paddingBottom': '4px',
                }),
            ]))
        inner = html.Div(className='mnid-grid3', children=cards)
    else:
        # Horizontal bar chart - sorted ascending so worst performer is at top
        sorted_data = sorted(data, key=lambda x: x[1])
        dists  = [d for d, _ in sorted_data]
        vals   = [_display_pct(v) for _, v in sorted_data]
        colors = [_cov_color(v) for v in vals]
        inner_bar_h = max(CHART_HEIGHT_MD, len(dists) * 24 + 40)
        outer_bar_h = _clamp_chart_height(inner_bar_h, CHART_HEIGHT_MD, CHART_HEIGHT_LG)

        fig = go.Figure(go.Bar(
            x=vals, y=dists,
            orientation='h',
            marker=dict(color=colors, line=dict(color='rgba(0,0,0,0)', width=0)),
            text=[f'{v:.0f}%' for v in vals],
            textposition='outside',
            textfont=dict(size=10, family=FONT),
            hovertemplate='<b>%{y}</b><br>Avg Coverage: %{x:.1f}%<extra></extra>',
        ))
        fig.add_vline(x=80, line_dash='dash', line_color=WARN_C, line_width=1.5,
                      annotation_text='Target 80%', annotation_font_size=9,
                      annotation_font_color=WARN_C, annotation_position='top right')
        fig.update_layout(
            paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family=FONT, size=10),
            height=inner_bar_h,
            margin=dict(l=8, r=60, t=12, b=24),
            xaxis=dict(
                range=[0, 110], showgrid=True, gridcolor=GRID_C, gridwidth=0.5,
                title=dict(text='Avg Coverage %', font=dict(size=9)),
                tickfont=dict(size=9),
            ),
            yaxis=dict(showgrid=False, tickfont=dict(size=10)),
        )
        inner = _graph_scroll_wrap(
            dcc.Graph(
                figure=fig,
                config={'displayModeBar': False},
                style=_graph_style(inner_bar_h),
            ),
            outer_bar_h,
        )

    return html.Div(style={'marginBottom': '14px'}, children=[
        html.Div('DISTRICT PERFORMANCE OVERVIEW', className='mnid-section-lbl'),
        inner,
    ])


# # MNID PPH management cascade funnel

def _pph_cascade(df):
    """PPH Management Cascade funnel chart."""
    try:
        def _n(col, val, col2=None, val2=None):
            if col not in df.columns:
                return 0
            mask = df[col].fillna('').str.upper().str.contains(val.upper(), na=False)
            sub  = df[mask]
            if col2 and val2 and col2 in sub.columns:
                sub = sub[sub[col2] == val2]
            return int(sub['person_id'].nunique())

        labor_n = _n('Encounter', 'LABOUR|DELIVERY|BIRTH')
        if labor_n == 0:
            return None

        stages = [
            ('Women in Labor',          labor_n),
            ('PPH Screening Performed', _n('concept_name', 'PPH screening')),
            ('PPH Detected',            _n('concept_name', 'PPH screening',
                                          'obs_value_coded', 'Positive')),
            ('Treatment Bundle',        _n('concept_name', 'PPH treatment bundle')),
        ]
        labels = [s[0] for s in stages]
        values = [s[1] for s in stages]

        if sum(values[1:]) == 0:
            return None

        colors = ['#2563EB', '#7C3AED', '#C2410C', '#0F766E']

        fig = go.Figure(go.Funnel(
            y=labels, x=values,
            textinfo='value+percent initial',
            textfont=dict(size=11, family=FONT),
            marker=dict(color=colors, line=dict(color=['#fff'] * 4, width=2)),
            connector=dict(line=dict(color=GRID_C, width=2)),
            hovertemplate='<b>%{y}</b><br>Count: %{x:,}<extra></extra>',
        ))
        fig.update_layout(
            **_CHART_LAYOUT,
            title=dict(text='PPH Management Cascade',
                       font=dict(size=12, color='#444441', family=FONT),
                       x=0, xanchor='left', y=0.98),
            height=280,
            margin=dict(l=8, r=8, t=36, b=8),
            showlegend=False,
        )
        return html.Div(className='mnid-chart-card', children=[
            dcc.Graph(figure=fig,
                      config={'displayModeBar': 'hover',
                              'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'],
                              'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                      style={'height': '280px'}),
        ])
    except Exception:
        return None


# MNID header, alert, KPI, and section navigation components

def _topbar(facility, period, n_tracked, n_await, facility_df=None, network_df=None,
            period_note=None, scope_meta=None,
            title='Maternal and Child Health Indicators', subtitle='Clean view of performance, comparison, coverage, and readiness.',
            theme='default'):
    facility_name = _FACILITY_NAMES.get(facility, facility or 'Network view')
    district = _FACILITY_DISTRICT.get(facility, 'All districts')

    source_df = facility_df if facility_df is not None and len(facility_df) else network_df
    if source_df is not None and len(source_df):
        if facility and 'Facility_CODE' in source_df.columns:
            fac_rows = source_df[source_df['Facility_CODE'].astype(str) == str(facility)]
        else:
            fac_rows = source_df
            facility_name = 'Network view' if len(source_df) else facility_name
            district = 'All districts' if len(source_df) else district
        if len(fac_rows):
            if 'Facility' in fac_rows.columns:
                names = fac_rows['Facility'].dropna().astype(str)
                if not names.empty:
                    facility_name = names.mode().iloc[0]
            if 'District' in fac_rows.columns:
                dists = fac_rows['District'].dropna().astype(str)
                if not dists.empty:
                    district = dists.mode().iloc[0]

    selected_program = 'Neonatal Care' if theme == 'newborn' else 'All'
    if facility_df is not None:
        requested = getattr(facility_df, 'attrs', {}).get('mnid_program')
        if requested and theme != 'newborn':
            selected_program = requested

    scope_meta = scope_meta or {}
    selected_facilities = [str(v).strip() for v in (scope_meta.get('selected_facilities') or []) if str(v).strip()]
    selected_districts = [str(v).strip() for v in (scope_meta.get('selected_districts') or []) if str(v).strip()]
    if selected_facilities:
        facility_name = selected_facilities[0] if len(selected_facilities) == 1 else f'{len(selected_facilities)} selected facilities'
    if selected_districts:
        district = selected_districts[0] if len(selected_districts) == 1 else ', '.join(selected_districts[:2]) + (f' +{len(selected_districts) - 2}' if len(selected_districts) > 2 else '')

    topbar_label = 'N-NID Dashboard' if theme == 'newborn' else 'M-NID Dashboard'
    newborn_focus = None
    if theme == 'newborn':
        newborn_focus = html.Div(className='mnid-topbar-highlight', children=[
            html.Div(className='mnid-topbar-highlight-copy', children=[
                html.Div('Neonatal service overview', className='mnid-topbar-highlight-title'),
                html.Div('View stabilization, respiratory support, KMC uptake, and facility performance in one place.',
                         className='mnid-topbar-highlight-subtitle'),
            ]),
            html.Div(className='mnid-topbar-highlight-chips', children=[
                html.Span('Stabilize', className='mnid-topbar-chip'),
                html.Span('Support', className='mnid-topbar-chip'),
                html.Span('Monitor', className='mnid-topbar-chip'),
                html.Span('Benchmark', className='mnid-topbar-chip'),
                html.Span(f'{n_tracked} available', className='mnid-topbar-chip strong'),
                html.Span(f'{n_await} pending', className='mnid-topbar-chip subtle'),
            ]),
        ])

    return html.Div(className=f'mnid-topbar{" mnid-topbar-newborn" if theme == "newborn" else ""}', children=[
        html.Div(className='mnid-topbar-copy', children=[
            html.Div(topbar_label, className='mnid-topbar-label'),
            html.H1(title),
            html.P(subtitle),
            newborn_focus,
        ]),
        html.Div(className='mnid-info-pills', children=[
            html.Div(className='mnid-info-pill', children=[
                html.Div('Facility', className='mnid-info-pill-label'),
                html.Div(facility_name, className='mnid-info-pill-value'),
            ]),
            html.Div(className='mnid-info-pill', children=[
                html.Div('District', className='mnid-info-pill-label'),
                html.Div(district, className='mnid-info-pill-value'),
            ]),
            html.Div(className='mnid-info-pill', children=[
                html.Div('Period', className='mnid-info-pill-label'),
                html.Div([
                    html.Div(period,
                             style={'fontSize': '11px', 'fontWeight': '700',
                                    'color': TEXT, 'lineHeight': '1.2'}),
                    html.Div(period_note,
                             style={'fontSize': '10px', 'color': MUTED, 'lineHeight': '1.3', 'marginTop': '4px'})
                    if period_note else None,
                ]),
            ]),
            html.Div(className='mnid-info-pill', children=[
                html.Div('Program', className='mnid-info-pill-label'),
                html.Div(
                    'Labour & Delivery' if selected_program == 'Labour' else selected_program,
                    className='mnid-info-pill-value mnid-info-pill-value-compact',
                ),
            ]),
            html.Div(className='mnid-info-pill', children=[
                html.Div('Indicators', className='mnid-info-pill-label'),
                html.Div(f'{n_tracked} available / {n_await} pending',
                         style={'fontSize': '11px', 'fontWeight': '700',
                                'color': TEXT, 'lineHeight': '1.2'}),
            ]),
        ]),
    ])


def _sidebar(facility_code: str, theme: str = 'default') -> html.Div:
    if theme == 'newborn':
        nav_items = [
            ('Overview',             '#mnid-summary'),
            ('Coverage',             '#mnid-coverage'),
            ('Run Charts',           '#mnid-trends'),
            ('District Performance', '#mnid-performance'),
            ('Geographic Coverage',  '#mnid-heatmap'),
            ('Facility Comparison',  '#mnid-comparative'),
        ]
    else:
        nav_items = [
            ('Overview',    '#mnid-summary'),
            ('Coverage',    '#mnid-coverage'),
            ('Run Charts',  '#mnid-trends'),
            ('Performance', '#mnid-performance'),
            ('Map View',    '#mnid-heatmap'),
            ('Comparison',  '#mnid-comparative'),
        ]
    return html.Div(className='mnid-nav', children=[
        html.A(
            id={'type': 'mnid-nav-btn', 'index': href},
            href=href,
            className='mnid-nav-btn active' if index == 0 else 'mnid-nav-btn',
            children=label,
        )
        for index, (label, href) in enumerate(nav_items)
    ])


def _alert_banner(below, strong):
    if not below:
        return html.Div(
            style={
                'display': 'flex', 'alignItems': 'center', 'gap': '10px',
                'background': '#F0FDF4', 'border': '1px solid #BBF7D0',
                'borderRadius': '10px', 'padding': '10px 14px',
                'marginBottom': '10px',
                'animation': 'mnid-ok-pop 0.5s cubic-bezier(.22,.68,0,1.2) both',
            },
            children=[
                html.Div('✓', style={
                    'width': '28px', 'height': '28px', 'borderRadius': '50%',
                    'background': '#16A34A', 'color': '#fff',
                    'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                    'fontSize': '14px', 'fontWeight': '800', 'flexShrink': '0',
                }),
                html.Div([
                    html.Span('All indicators on target. ', style={
                        'fontWeight': '700', 'fontSize': '12px', 'color': '#14532D',
                    }),
                    html.Span(
                        f'{len(strong)} strong area{"s" if len(strong) != 1 else ""}: '
                        + (', '.join(strong[:5]) + ('…' if len(strong) > 5 else '')),
                        style={'fontSize': '11px', 'color': '#166534'},
                    ),
                ]),
            ]
        )

    n_below = len(below)
    n_strong = len(strong)
    slot = 3.5
    total = n_below * slot
    kf_name = f'mnid-alert-rotate-{min(n_below, 15)}'

    def _item(name, pct, i):
        is_bad = pct < 50
        bg   = '#FEE2E2' if is_bad else '#FEF3C7'
        fg   = '#991B1B' if is_bad else '#92400E'
        icon = '▼' if is_bad else '↘'
        return html.Div(
            style={
                'position': 'absolute', 'top': '0', 'left': '0',
                'display': 'flex', 'alignItems': 'center', 'gap': '6px',
                'opacity': 0,
                'animation': f'{kf_name} {total:.1f}s {i * slot:.1f}s ease-in-out infinite',
                'animationFillMode': 'both',
            },
            children=[
                html.Span(f'{icon} {name[:36]}', style={
                    'fontSize': '12px', 'fontWeight': '600', 'color': fg,
                    'background': bg, 'padding': '3px 10px', 'borderRadius': '999px',
                    'whiteSpace': 'nowrap',
                }),
                html.Span(f'{pct:.0f}%', style={
                    'fontSize': '13px', 'fontWeight': '800', 'color': fg,
                }),
            ]
        )

    items = [_item(n, p, i) for i, (n, p) in enumerate(below)]

    return html.Div(
        style={
            'display': 'flex', 'alignItems': 'center', 'gap': '12px',
            'background': '#FFF7ED', 'border': '1px solid #FED7AA',
            'borderRadius': '10px', 'padding': '10px 14px',
            'marginBottom': '10px',
        },
        children=[
            html.Div(style={
                'display': 'flex', 'flexDirection': 'column',
                'alignItems': 'center', 'gap': '3px', 'flexShrink': '0',
            }, children=[
                html.Div(style={
                    'width': '10px', 'height': '10px', 'borderRadius': '50%',
                    'background': '#EF4444',
                    'animation': 'mnid-dot-blink 1.3s ease-in-out infinite',
                }),
                html.Span(f'{n_below}', style={
                    'fontSize': '15px', 'fontWeight': '800', 'color': '#DC2626', 'lineHeight': '1',
                }),
                html.Span('below', style={'fontSize': '8px', 'color': '#9A3412', 'lineHeight': '1'}),
            ]),
            html.Div(style={'width': '1px', 'height': '38px', 'background': '#FED7AA', 'flexShrink': '0'}),
            html.Div(style={'position': 'relative', 'height': '28px', 'flex': '1', 'minWidth': '0'}, children=items),
            html.Div(style={'flexShrink': '0', 'textAlign': 'center'}, children=[
                html.Span(f'{n_strong}', style={
                    'fontSize': '15px', 'fontWeight': '800', 'color': '#16A34A', 'lineHeight': '1',
                }),
                html.Div('on target', style={'fontSize': '8px', 'color': '#166534'}),
            ]) if n_strong else None,
        ]
    )


def _avg_ring(pct: float, color: str) -> html.Div:
    """Prominent donut ring - the ring IS the value display for avg coverage card."""
    p = max(0.0, min(pct, 100.0))
    # Choose font size based on length
    font_size = '11px' if p < 100 else '9px'
    return html.Div(style={
        'width': '62px', 'height': '62px', 'borderRadius': '50%',
        'background': f'conic-gradient({color} {p:.1f}%, {GRID_C} 0)',
        'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
        'flexShrink': '0',
        'filter': 'drop-shadow(0 2px 6px rgba(0,0,0,0.10))',
    }, children=[
        html.Div(style={
            'width': '44px', 'height': '44px', 'borderRadius': '50%',
            'background': BG,
            'display': 'flex', 'flexDirection': 'column',
            'alignItems': 'center', 'justifyContent': 'center',
            'gap': '1px',
        }, children=[
            html.Span(f'{_display_pct(p):.0f}%', style={
                'fontSize': font_size, 'fontWeight': '700',
                'color': color, 'lineHeight': '1',
            }),
            html.Span('avg', style={
                'fontSize': '7px', 'color': MUTED, 'lineHeight': '1',
            }),
        ]),
    ])


def _count_bar(count: int, total: int, color: str) -> html.Div:
    """Thin coloured bottom stripe showing proportion of total."""
    fill = round(count / total * 100) if total else 0
    return html.Div(style={
        'position': 'absolute', 'bottom': '0', 'left': '0', 'right': '0',
        'height': '3px', 'background': GRID_C, 'borderRadius': '0 0 10px 10px',
    }, children=[
        html.Div(style={
            'width': f'{fill}%', 'height': '100%',
            'background': color, 'borderRadius': '0 0 0 10px',
            'transition': 'width 0.5s ease',
        }),
    ])


def _kpi(label, value, sub, cls, bottom_bar=None, ring=None):
    return html.Div(className=f'mnid-kpi {cls}', children=[
        html.Div(style={'display': 'flex', 'justifyContent': 'space-between',
                        'alignItems': 'flex-start', 'gap': '6px'}, children=[
            html.Div([
                html.Div(label, className='kpi-lbl'),
                html.Div(value, className='kpi-val'),
                html.Div(sub,   className='kpi-sub'),
            ]),
            ring or html.Div(),
        ]),
        bottom_bar or html.Div(),
    ])


def _kpi_row(computed):
    n    = len(computed)
    on   = [c for c in computed if _css(c['pct'], c['target'], c) == 'ok']
    mon  = [c for c in computed if _css(c['pct'], c['target'], c) == 'warn']
    crit = [c for c in computed if _css(c['pct'], c['target'], c) == 'danger']
    avg  = round(sum(c.get('attained_pct', _target_attainment_pct(c['pct'], c['target'], c)) for c in computed) / n, 1) if n else 0.0
    avg_color = _cov_color(avg)
    return html.Div(className='mnid-kpi-row', children=[
        _kpi('Available Indicators', str(n), 'live indicators', 'info',
             bottom_bar=_count_bar(n, n, INFO_C)),
        _kpi('On Target', str(len(on)), 'meeting benchmark', 'ok',
             bottom_bar=_count_bar(len(on), n, OK_C)),
        _kpi('Watch', str(len(mon)), 'near target', 'warn',
             bottom_bar=_count_bar(len(mon), n, WARN_C)),
        _kpi('Needs Review', str(len(crit)), 'below target', 'danger',
             bottom_bar=_count_bar(len(crit), n, DANGER_C)),
        _kpi('Average Coverage', '', 'across available indicators', 'info',
             ring=_avg_ring(avg, avg_color)),
    ])


# MNID section anchor helper

def _section_anchor(anchor_id):
    """Invisible offset anchor for sticky-nav scrolling."""
    return html.Div(id=anchor_id, className='mnid-section-anchor')
