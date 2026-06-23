"""Unified MNH MoH dashboard view built from existing MNID data and indicator metadata."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from helpers.helpers import build_single_chart
from mnid.aggregation.store import get_aggregate as _get_aggregate, query_coverage as _agg_coverage
from mnid.charts.chart_helpers import _cov
from mnid.core.cache import _resolve_scope_filters
from mnid.core.constants import BORDER, DIM, GRID_C, TEXT
from mnid.core.indicators import _resolve_category_order, _resolve_runtime_mnid_indicators

_SECTION_ORDER = [
    ('Overview', {'ANC', 'Labour', 'PNC', 'Newborn'}),
    ('Antenatal Care', {'ANC'}),
    ('Labour and Delivery', {'Labour'}),
    ('Maternal Outcomes', {'Labour', 'PNC'}),
    ('Newborn and Birth Outcomes', {'Newborn', 'Labour'}),
    ('Postnatal Care', {'PNC'}),
    ('HIV and PMTCT', {'ANC', 'PNC'}),
    ('Referrals and Complications', {'ANC', 'Labour', 'PNC', 'Newborn'}),
    ('Quality of Care / Signal Functions', {'ANC', 'Labour', 'PNC', 'Newborn'}),
    ('Data Quality', set()),
]

_SECTION_LABEL_RULES = {
    'Maternal Outcomes': ('death', 'live birth', 'stillbirth', 'caesarean'),
    'Newborn and Birth Outcomes': ('newborn', 'neonatal', 'birth weight', 'vitamin k', 'kmc', 'phototherapy', 'cpap'),
    'HIV and PMTCT': ('hiv', 'syphilis'),
    'Referrals and Complications': ('complication', 'referral', 'pph', 'eclampsia', 'sepsis'),
    'Quality of Care / Signal Functions': ('partograph', 'blood pressure', 'temperature', 'pulse oximeter', 'bilirubin', 'resuscitation', 'magnesium', 'antibiotic', 'screened'),
}

_SECTION_IDS = {
    'Overview': 'mnh-moh-overview',
    'Antenatal Care': 'mnh-moh-anc',
    'Labour and Delivery': 'mnh-moh-labour',
    'Maternal Outcomes': 'mnh-moh-maternal',
    'Newborn and Birth Outcomes': 'mnh-moh-newborn',
    'Postnatal Care': 'mnh-moh-pnc',
    'HIV and PMTCT': 'mnh-moh-hiv',
    'Referrals and Complications': 'mnh-moh-referrals',
    'Quality of Care / Signal Functions': 'mnh-moh-quality',
    'Operational Readiness and Signal Functions': 'mnh-moh-quality',
    'Data Quality': 'mnh-moh-data-quality',
}


def _safe_pct(num: int, den: int) -> float:
    return round((num / den) * 100, 1) if den else 0.0


def _period_label(start_date, end_date) -> str:
    start_ts = pd.to_datetime(start_date, errors='coerce')
    end_ts = pd.to_datetime(end_date, errors='coerce')
    if pd.isna(start_ts) or pd.isna(end_ts):
        return 'Current reporting window'
    return f"{start_ts.strftime('%d %b %Y')} to {end_ts.strftime('%d %b %Y')}"


def _find_indicator_value(indicators: list[dict], labels: tuple[str, ...]) -> int:
    wanted = {label.lower() for label in labels}
    for indicator in indicators:
        if str(indicator.get('label', '')).lower() in wanted:
            return int(indicator.get('numerator', 0) or 0)
    return 0


def _compute_indicator(df: pd.DataFrame, indicator: dict, agg_df: pd.DataFrame | None,
                       start_date, end_date, facility_codes: list[str] | None,
                       districts: list[str] | None) -> dict:
    num = den = 0
    pct = 0.0
    if agg_df is not None:
        try:
            num, den, pct = _agg_coverage(
                agg_df,
                indicator['id'],
                pd.to_datetime(start_date).normalize(),
                pd.to_datetime(end_date).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1),
                facility_codes=facility_codes or None,
                districts=districts or None,
                grain='monthly',
                indicator_label=indicator.get('label'),
            )
        except Exception:
            num = den = 0
    if not den:
        num, den, pct = _cov(df, indicator.get('numerator_filters', {}), indicator.get('denominator_filters', {}))
    return {
        **indicator,
        'numerator': int(num),
        'denominator': int(den),
        'pct': float(pct or 0.0),
    }


def _badge(text: str, color: str, bg: str) -> html.Span:
    return html.Span(
        text,
        style={
            'display': 'inline-flex',
            'alignItems': 'center',
            'padding': '3px 10px',
            'borderRadius': '999px',
            'fontSize': '11px',
            'fontWeight': 700,
            'color': color,
            'background': bg,
        },
    )


def _status_badge(pct: float, target: float | None, target_mode: str | None = None) -> html.Span:
    if target is None:
        return _badge('Observed', '#1D4ED8', '#DBEAFE')
    if target_mode == 'min':
        okay = pct <= target
    else:
        okay = pct >= target
    return _badge('On track' if okay else 'Needs attention', '#166534' if okay else '#991B1B', '#DCFCE7' if okay else '#FEE2E2')


def _module_tabs(section_names: list[str]) -> html.Div:
    return html.Div(
        style={
            'display': 'flex',
            'gap': '2px',
            'overflowX': 'auto',
            'padding': '0 2px',
            'marginBottom': '18px',
            'background': '#FFFFFF',
            'border': f'1px solid {BORDER}',
            'borderRadius': '18px',
            'boxShadow': '0 10px 24px rgba(15, 23, 42, 0.04)',
        },
        children=[
            html.A(
                section_name,
                href=f"#{_SECTION_IDS.get(section_name, '')}",
                style={
                    'display': 'inline-flex',
                    'alignItems': 'center',
                    'padding': '12px 16px',
                    'borderRadius': '16px',
                    'border': '1px solid transparent',
                    'background': '#FFFFFF',
                    'color': '#475569',
                    'fontSize': '12px',
                    'fontWeight': 700,
                    'textDecoration': 'none',
                    'whiteSpace': 'nowrap',
                    'margin': '2px 0',
                },
            )
            for section_name in section_names
        ],
    )


def _meta_bar(period_text: str, active_districts: int, active_facilities: int, completeness: float) -> html.Div:
    items = [
        ('Reporting period', period_text),
        ('District scope', f'{active_districts} districts'),
        ('Reporting facilities', f'{active_facilities} facilities'),
        ('Completeness proxy', f'{completeness:.1f}%'),
    ]
    return html.Div(
        style={
            'display': 'flex',
            'gap': '20px',
            'flexWrap': 'wrap',
            'marginBottom': '18px',
            'padding': '12px 16px',
            'background': '#FFFFFF',
            'border': f'1px solid {BORDER}',
            'borderRadius': '16px',
            'boxShadow': '0 10px 24px rgba(15, 23, 42, 0.04)',
        },
        children=[
            html.Div(
                style={
                    'minWidth': '150px',
                },
                children=[
                    html.Div(label, style={'fontSize': '10px', 'fontWeight': 800, 'letterSpacing': '0.08em', 'textTransform': 'uppercase', 'color': DIM}),
                    html.Div(value, style={'fontSize': '13px', 'fontWeight': 700, 'color': '#334155', 'marginTop': '4px'}),
                ],
            )
            for label, value in items
        ],
    )


def _priority_alert(maternal_deaths: int, neonatal_deaths: int, stillbirths: int, complication_burden: int) -> html.Div:
    total_events = maternal_deaths + neonatal_deaths + stillbirths + complication_burden
    title = 'Priority outcomes require attention' if total_events else 'No critical mortality alerts recorded'
    subtitle = (
        'Maternal deaths, neonatal deaths, stillbirths, and complication burden are summarized here for rapid Ministry-level review.'
        if total_events else
        'The selected reporting window has no recorded maternal, neonatal, or stillbirth events in the current scope.'
    )
    tone_bg = '#FFF7ED' if total_events else '#F0FDF4'
    tone_border = '#FED7AA' if total_events else '#BBF7D0'
    return html.Div(
        style={
            'display': 'flex',
            'alignItems': 'center',
            'gap': '16px',
            'flexWrap': 'wrap',
            'padding': '16px 18px',
            'borderRadius': '18px',
            'background': tone_bg,
            'border': f'1px solid {tone_border}',
            'marginBottom': '18px',
        },
        children=[
            html.Div(
                style={'minWidth': '84px', 'textAlign': 'center'},
                children=[
                    html.Div(f'{total_events:,}', style={'fontSize': '28px', 'fontWeight': 900, 'lineHeight': '1', 'color': '#B45309' if total_events else '#166534'}),
                    html.Div('events', style={'fontSize': '10px', 'color': '#92400E' if total_events else '#166534', 'marginTop': '3px'}),
                ],
            ),
            html.Div(style={'width': '1px', 'alignSelf': 'stretch', 'background': tone_border}),
            html.Div([
                html.Div('Priority Alert', style={'fontSize': '11px', 'fontWeight': 800, 'letterSpacing': '0.08em', 'textTransform': 'uppercase', 'color': '#9A3412' if total_events else '#166534'}),
                html.Div(title, style={'fontSize': '18px', 'fontWeight': 900, 'color': TEXT, 'marginTop': '4px'}),
                html.Div(subtitle, style={'fontSize': '12px', 'lineHeight': '1.55', 'color': '#6B7280', 'marginTop': '4px', 'maxWidth': '520px'}),
            ], style={'flex': '1 1 280px'}),
            html.Div(
                style={'display': 'flex', 'gap': '16px', 'flexWrap': 'wrap', 'marginLeft': 'auto'},
                children=[
                    html.Div([
                        html.Div(label, style={'fontSize': '10px', 'fontWeight': 800, 'letterSpacing': '0.06em', 'textTransform': 'uppercase', 'color': DIM}),
                        html.Div(f'{value:,}', style={'fontSize': '18px', 'fontWeight': 900, 'color': color, 'marginTop': '4px'}),
                    ], style={'minWidth': '110px'})
                    for label, value, color in [
                        ('Maternal deaths', maternal_deaths, '#E11D48'),
                        ('Neonatal deaths', neonatal_deaths, '#D97706'),
                        ('Stillbirths', stillbirths, '#7C3AED'),
                        ('Complications', complication_burden, '#0F766E'),
                    ]
                ],
            ),
        ],
    )


def _hero_card(title: str, value: str, subtext: str, accent: str) -> html.Div:
    return html.Div(
        style={
            'border': f'1px solid {BORDER}',
            'borderTop': f'4px solid {accent}',
            'borderRadius': '0 0 14px 14px',
            'padding': '14px 16px',
            'background': '#FFFFFF',
            'boxShadow': '0 8px 22px rgba(15, 23, 42, 0.04)',
        },
        children=[
            html.Div(title, style={'fontSize': '12px', 'fontWeight': 700, 'color': DIM, 'textTransform': 'uppercase', 'letterSpacing': '0.06em'}),
            html.Div(value, style={'fontSize': '24px', 'fontWeight': 800, 'color': TEXT, 'marginTop': '8px', 'lineHeight': '1.2'}),
            html.Div(subtext, style={'fontSize': '11px', 'color': DIM, 'marginTop': '6px', 'lineHeight': '1.45'}),
        ],
    )


def _indicator_card(indicator: dict) -> html.Div:
    target = indicator.get('target')
    pct = indicator.get('pct', 0.0)
    fill_color = '#15803D' if pct >= (target or 0.0) else '#D97706'
    return html.Div(
        style={
            'border': f'1px solid {BORDER}',
            'borderRadius': '14px',
            'padding': '16px',
            'background': '#FFFFFF',
            'display': 'flex',
            'flexDirection': 'column',
            'gap': '10px',
            'boxShadow': '0 8px 24px rgba(15, 23, 42, 0.04)',
        },
        children=[
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-between', 'gap': '12px', 'alignItems': 'flex-start'},
                children=[
                    html.Div([
                        html.Div(indicator.get('category', ''), style={'fontSize': '10px', 'fontWeight': 800, 'color': '#6B7280', 'textTransform': 'uppercase', 'letterSpacing': '0.06em'}),
                        html.Div(indicator.get('label', ''), style={'fontSize': '14px', 'fontWeight': 700, 'color': TEXT, 'marginTop': '6px', 'lineHeight': '1.4'}),
                    ]),
                    _status_badge(indicator.get('pct', 0.0), target, indicator.get('target_mode')),
                ],
            ),
            html.Div(f"{pct:.1f}%", style={'fontSize': '28px', 'fontWeight': 800, 'color': '#0F172A'}),
            html.Div(
                [
                    html.Span(f"{indicator.get('numerator', 0):,}", style={'fontWeight': 700, 'color': '#111827'}),
                    html.Span(' of ', style={'color': DIM}),
                    html.Span(f"{indicator.get('denominator', 0):,}", style={'fontWeight': 700, 'color': '#111827'}),
                    html.Span(' eligible records', style={'color': DIM}),
                ],
                style={'fontSize': '12px'},
            ),
            html.Div(
                [
                    html.Div(
                        style={
                            'height': '8px',
                            'width': '100%',
                            'borderRadius': '999px',
                            'background': GRID_C,
                            'overflow': 'hidden',
                        },
                        children=html.Div(
                            style={
                                'height': '100%',
                                'width': f"{max(0.0, min(pct, 100.0)):.1f}%",
                                'background': fill_color,
                            }
                        ),
                    ),
                    html.Div(
                        f"Target {target:.0f}%" if target is not None else 'No target configured',
                        style={'fontSize': '11px', 'color': DIM, 'marginTop': '6px'},
                    ),
                ]
            ),
            html.Div(indicator.get('note') or '', style={'fontSize': '11px', 'color': DIM}),
        ],
    )


def _section_shell(title: str, description: str, children: list) -> html.Div:
    return html.Div(
        id=_SECTION_IDS.get(title),
        style={'marginTop': '26px', 'scrollMarginTop': '84px'},
        children=[
            html.Div(
                style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'marginBottom': '8px'},
                children=[
                    html.Div(style={'width': '4px', 'height': '20px', 'borderRadius': '999px', 'background': '#166534'}),
                    html.Div(title, style={'fontSize': '12px', 'fontWeight': 800, 'letterSpacing': '0.08em', 'textTransform': 'uppercase', 'color': '#475569'}),
                ],
            ),
            html.Div(description, style={'fontSize': '13px', 'color': DIM, 'marginBottom': '14px'}),
            html.Div(
                children,
                style={
                    'display': 'grid',
                    'gridTemplateColumns': 'repeat(auto-fit, minmax(260px, 1fr))',
                    'gap': '14px',
                },
            ),
        ],
    )


def _service_volume_fig(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty or 'Date' not in df.columns or 'Service_Area' not in df.columns or 'person_id' not in df.columns:
        fig.update_layout(height=320, paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF')
        return fig

    chart_df = df.copy()
    chart_df['month'] = pd.to_datetime(chart_df['Date'], errors='coerce').dt.to_period('M').dt.to_timestamp()
    chart_df = chart_df.dropna(subset=['month'])
    grouped = (
        chart_df.groupby(['month', 'Service_Area'])['person_id']
        .nunique()
        .reset_index(name='clients')
        .sort_values('month')
    )
    for service_area in ['ANC', 'Labour', 'PNC', 'Newborn']:
        service_df = grouped[grouped['Service_Area'] == service_area]
        if service_df.empty:
            continue
        fig.add_trace(go.Scatter(
            x=service_df['month'],
            y=service_df['clients'],
            mode='lines+markers',
            name=service_area,
            line=dict(width=3),
        ))
    fig.update_layout(
        title='Monthly service volumes',
        height=320,
        margin=dict(l=20, r=20, t=54, b=20),
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0),
        font=dict(color=TEXT),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor=GRID_C, title='Distinct clients')
    return fig


def _outcome_mix_fig(indicators: list[dict]) -> go.Figure:
    outcome_labels = []
    outcome_values = []
    for indicator in indicators:
        label = str(indicator.get('label', ''))
        label_lower = label.lower()
        if any(token in label_lower for token in ('maternal deaths', 'newborn deaths', 'neonatal deaths', 'stillbirths', 'live births', 'outborn babies')):
            outcome_labels.append(label)
            outcome_values.append(indicator.get('numerator', 0))
    fig = go.Figure()
    if outcome_labels:
        fig.add_trace(go.Bar(x=outcome_labels, y=outcome_values, marker_color=['#E11D48', '#F97316', '#0284C7', '#16A34A', '#7C3AED', '#0EA5E9'][:len(outcome_labels)]))
    fig.update_layout(
        title='Outcome counts in the selected window',
        height=320,
        margin=dict(l=20, r=20, t=54, b=20),
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        font=dict(color=TEXT),
    )
    fig.update_xaxes(showgrid=False, tickangle=-15)
    fig.update_yaxes(gridcolor=GRID_C, title='Clients')
    return fig


def _chart_block(title: str, figure: go.Figure) -> html.Div:
    return html.Div(
        style={
            'border': f'1px solid {BORDER}',
            'borderRadius': '14px',
            'padding': '14px',
            'background': '#FFFFFF',
            'boxShadow': '0 10px 24px rgba(15, 23, 42, 0.04)',
        },
        children=[
            html.Div(title, style={'fontSize': '14px', 'fontWeight': 700, 'color': TEXT, 'padding': '2px 2px 0'}),
            dcc.Graph(figure=figure, config={'displayModeBar': False, 'responsive': True}, style={'height': '320px'}),
        ],
    )


def _summary_header(period_text: str, active_districts: int, active_facilities: int, completeness: float) -> html.Div:
    return html.Div(
        style={
            'display': 'flex',
            'justifyContent': 'space-between',
            'alignItems': 'center',
            'gap': '12px',
            'flexWrap': 'wrap',
            'padding': '14px 18px',
            'background': '#FFFFFF',
            'border': f'1px solid {BORDER}',
            'borderRadius': '18px',
            'boxShadow': '0 10px 24px rgba(15, 23, 42, 0.04)',
            'marginBottom': '16px',
        },
        children=[
            html.Div(
                style={'display': 'flex', 'alignItems': 'center', 'gap': '10px'},
                children=[
                    html.Div('MNH-MOH Dashboard', style={'fontSize': '15px', 'fontWeight': 800, 'color': TEXT}),
                    _badge('Live', '#166534', '#E8F7EF'),
                ],
            ),
            html.Div(
                style={'display': 'flex', 'gap': '8px', 'flexWrap': 'wrap'},
                children=[
                    _badge(period_text, '#475569', '#F8FAFC'),
                    _badge(f'{active_districts} Districts', '#475569', '#F8FAFC'),
                    _badge(f'{active_facilities} Facilities', '#475569', '#F8FAFC'),
                    _badge(f'Completeness {completeness:.1f}%', '#166534', '#ECFDF5'),
                ],
            ),
        ],
    )


def _mortality_card(title: str, count: int, rate_label: str, rate_value: float, tone: str, subtitle: str) -> html.Div:
    tones = {
        'red': {'bg': '#FEF2F2', 'border': '#FCA5A5', 'text': '#B91C1C', 'dot': '#DC2626'},
        'amber': {'bg': '#FFFBEB', 'border': '#FCD34D', 'text': '#B45309', 'dot': '#D97706'},
        'purple': {'bg': '#F5F3FF', 'border': '#C4B5FD', 'text': '#6D28D9', 'dot': '#7C3AED'},
    }
    palette = tones[tone]
    return html.Div(
        style={
            'background': palette['bg'],
            'border': f"1px solid {palette['border']}",
            'borderRadius': '16px',
            'padding': '18px',
        },
        children=[
            html.Div(
                style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'marginBottom': '10px'},
                children=[
                    html.Div(style={'width': '8px', 'height': '8px', 'borderRadius': '999px', 'background': palette['dot']}),
                    html.Div(title, style={'fontSize': '11px', 'fontWeight': 800, 'letterSpacing': '0.06em', 'textTransform': 'uppercase', 'color': palette['text']}),
                ],
            ),
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-between', 'gap': '12px', 'alignItems': 'flex-end'},
                children=[
                    html.Div(f'{count:,}', style={'fontSize': '42px', 'fontWeight': 900, 'lineHeight': '1', 'color': palette['text']}),
                    html.Div(
                        style={'textAlign': 'right'},
                        children=[
                            html.Div('Current period', style={'fontSize': '9px', 'fontWeight': 700, 'letterSpacing': '0.06em', 'textTransform': 'uppercase', 'color': '#9CA3AF'}),
                            html.Div('Needs attention' if count else 'Stable', style={'fontSize': '11px', 'fontWeight': 800, 'color': palette['text'], 'marginTop': '4px'}),
                        ],
                    ),
                ],
            ),
            html.Div(subtitle, style={'fontSize': '11px', 'color': '#6B7280', 'marginTop': '8px'}),
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'flex-end', 'marginTop': '12px', 'paddingTop': '10px', 'borderTop': '1px solid rgba(15, 23, 42, 0.08)'},
                children=[
                    html.Div(
                        children=[
                            html.Div(rate_label, style={'fontSize': '10px', 'color': '#9CA3AF', 'marginBottom': '2px'}),
                            html.Div(f'{rate_value:,.1f}', style={'fontSize': '14px', 'fontWeight': 800, 'color': '#334155'}),
                        ]
                    ),
                    html.Div(_badge('Observed' if count else 'None recorded', palette['text'], '#FFFFFFB8')),
                ],
            ),
        ],
    )


def _summary_rail(narrative: list[str], selected_districts: list[str], selected_facilities: list[str],
                  service_clients: dict[str, int], active_facilities: int, active_districts: int) -> html.Div:
    if selected_facilities:
        scope_line = f"Facility focus: {', '.join(selected_facilities[:3])}{'...' if len(selected_facilities) > 3 else ''}"
    elif selected_districts:
        scope_line = f"District focus: {', '.join(selected_districts[:4])}{'...' if len(selected_districts) > 4 else ''}"
    else:
        scope_line = 'National or full accessible scope is currently applied.'
    stat_rows = [
        ('ANC', service_clients.get('ANC', 0), '#166534'),
        ('Labour', service_clients.get('Labour', 0), '#0F766E'),
        ('PNC', service_clients.get('PNC', 0), '#2563EB'),
        ('Newborn', service_clients.get('Newborn', 0), '#7C3AED'),
    ]
    max_value = max((value for _, value, _ in stat_rows), default=0) or 1
    return html.Div(
        style={
            'background': '#FFFFFF',
            'border': f'1px solid {BORDER}',
            'borderRadius': '18px',
            'padding': '18px',
            'boxShadow': '0 10px 24px rgba(15, 23, 42, 0.04)',
            'height': '100%',
        },
        children=[
            html.Div('Situation room', style={'fontSize': '11px', 'fontWeight': 800, 'letterSpacing': '0.08em', 'textTransform': 'uppercase', 'color': '#6B7280'}),
            html.Div(scope_line, style={'fontSize': '16px', 'fontWeight': 800, 'color': TEXT, 'marginTop': '8px', 'lineHeight': '1.35'}),
            html.Div(' '.join(narrative), style={'fontSize': '12px', 'color': DIM, 'lineHeight': '1.55', 'marginTop': '8px'}),
            html.Div(
                style={'display': 'grid', 'gridTemplateColumns': 'repeat(2, minmax(0, 1fr))', 'gap': '10px', 'marginTop': '16px'},
                children=[
                    html.Div([
                        html.Div('Districts in scope', style={'fontSize': '10px', 'fontWeight': 800, 'letterSpacing': '0.06em', 'textTransform': 'uppercase', 'color': '#9CA3AF'}),
                        html.Div(f'{active_districts:,}', style={'fontSize': '22px', 'fontWeight': 900, 'color': TEXT, 'marginTop': '4px'}),
                    ]),
                    html.Div([
                        html.Div('Facilities reporting', style={'fontSize': '10px', 'fontWeight': 800, 'letterSpacing': '0.06em', 'textTransform': 'uppercase', 'color': '#9CA3AF'}),
                        html.Div(f'{active_facilities:,}', style={'fontSize': '22px', 'fontWeight': 900, 'color': TEXT, 'marginTop': '4px'}),
                    ]),
                ],
            ),
            html.Div('Service mix', style={'fontSize': '10px', 'fontWeight': 800, 'letterSpacing': '0.06em', 'textTransform': 'uppercase', 'color': '#9CA3AF', 'marginTop': '18px', 'marginBottom': '8px'}),
            html.Div(
                children=[
                    html.Div(
                        style={'marginBottom': '10px'},
                        children=[
                            html.Div(
                                style={'display': 'flex', 'justifyContent': 'space-between', 'fontSize': '11px', 'marginBottom': '4px'},
                                children=[
                                    html.Span(label, style={'fontWeight': 700, 'color': '#334155'}),
                                    html.Span(f'{value:,}', style={'fontWeight': 800, 'color': color}),
                                ],
                            ),
                            html.Div(
                                style={'height': '8px', 'background': '#E5E7EB', 'borderRadius': '999px', 'overflow': 'hidden'},
                                children=html.Div(
                                    style={'height': '100%', 'width': f'{(value / max_value) * 100:.1f}%', 'background': color, 'borderRadius': '999px'}
                                ),
                            ),
                        ],
                    )
                    for label, value, color in stat_rows
                ]
            ),
        ],
    )


def _select_section(label: str, category: str) -> str:
    label_lower = label.lower()
    for section_name, tokens in _SECTION_LABEL_RULES.items():
        if any(token in label_lower for token in tokens):
            return section_name
    if category == 'ANC':
        return 'Antenatal Care'
    if category == 'Labour':
        return 'Labour and Delivery'
    if category == 'PNC':
        return 'Postnatal Care'
    if category == 'Newborn':
        return 'Newborn and Birth Outcomes'
    return 'Overview'


def _materialize_chart_items(chart_sections: list[dict], df: pd.DataFrame) -> list:
    items = []
    for section in chart_sections:
        for chart_item in section.get('items', []):
            if chart_item.get('type') == 'Line':
                continue
            items.append(build_single_chart(df, df, 30, chart_item, style='card-2'))
            if len(items) >= 6:
                return items
    return items


def render_mnh_moh_dashboard(
    facility_df: pd.DataFrame,
    network_df: pd.DataFrame,
    maternal_config: dict,
    newborn_config: dict | None,
    start_date,
    end_date,
    scope_meta: dict | None = None,
) -> html.Div:
    scope_meta = scope_meta or {}
    working_df = facility_df.copy() if facility_df is not None else pd.DataFrame()
    if working_df.empty:
        return html.Div('No MNH MoH data available for the selected filters.', style={'padding': '24px', 'color': DIM})
    selected_facilities, selected_facility_codes, selected_districts = _resolve_scope_filters(network_df, scope_meta)
    district_filter = None if selected_facility_codes else (selected_districts or None)

    maternal_inds = maternal_config.get('priority_indicators') or []
    newborn_inds = (newborn_config or {}).get('priority_indicators') or []
    combined_inds = []
    seen_ids = set()
    for indicator in maternal_inds + newborn_inds:
        indicator_id = str(indicator.get('id') or '').strip()
        if not indicator_id or indicator_id in seen_ids:
            continue
        seen_ids.add(indicator_id)
        combined_inds.append(indicator)

    combined_inds = _resolve_runtime_mnid_indicators(
        combined_inds,
        working_df,
        categories=['ANC', 'Labour', 'PNC', 'Newborn'],
    )
    category_order = _resolve_category_order(combined_inds, ['ANC', 'Labour', 'PNC', 'Newborn'])

    agg_df = _get_aggregate()
    computed_indicators = [
        _compute_indicator(
            working_df,
            indicator,
            agg_df,
            start_date,
            end_date,
            selected_facility_codes or None,
            district_filter,
        )
        for indicator in combined_inds
        if indicator.get('status') != 'awaiting_baseline'
    ]

    overview_indicators = [item for item in computed_indicators if item.get('status') == 'overview_only']
    tracked_indicators = [item for item in computed_indicators if item.get('status') != 'overview_only']

    service_clients = {
        service: int(working_df.loc[working_df['Service_Area'].eq(service), 'person_id'].astype(str).nunique())
        for service in category_order
        if {'Service_Area', 'person_id'}.issubset(working_df.columns)
    }
    active_facilities = int(working_df['Facility_CODE'].astype(str).nunique()) if 'Facility_CODE' in working_df.columns else 0
    active_districts = int(working_df['District'].astype(str).nunique()) if 'District' in working_df.columns else 0
    completeness = _safe_pct(
        int(working_df['person_id'].notna().sum()) if 'person_id' in working_df.columns else 0,
        len(working_df),
    )

    sections = defaultdict(list)
    for indicator in tracked_indicators:
        sections[_select_section(indicator.get('label', ''), indicator.get('category', ''))].append(indicator)

    chart_items = _materialize_chart_items(maternal_config.get('visualization_types', {}).get('charts', {}).get('sections', []), working_df)
    readiness_source = []
    for key in ('workforce_indicators', 'supply_indicators', 'data_quality_indicators'):
        readiness_source.extend(maternal_config.get(key) or maternal_config.get('visualization_types', {}).get(key, []))
        if newborn_config:
            readiness_source.extend(newborn_config.get(key) or newborn_config.get('visualization_types', {}).get(key, []))
    readiness_indicators = []
    seen_ids.clear()
    for indicator in readiness_source:
        indicator_id = str(indicator.get('id') or indicator.get('label') or '').strip()
        if not indicator_id or indicator_id in seen_ids:
            continue
        seen_ids.add(indicator_id)
        readiness_indicators.append(_compute_indicator(
            working_df,
            indicator,
            agg_df,
            start_date,
            end_date,
            selected_facility_codes or None,
            district_filter,
        ))

    hero_cards = [
        _hero_card('Reporting window', _period_label(start_date, end_date), f'{active_districts} districts and {active_facilities} facilities in scope', '#0F172A'),
        _hero_card('ANC clients', f"{service_clients.get('ANC', 0):,}", 'Distinct ANC clients in the filtered period', '#15803D'),
        _hero_card('Deliveries / labour', f"{service_clients.get('Labour', 0):,}", 'Distinct labour and delivery clients', '#B45309'),
        _hero_card('PNC + newborn', f"{service_clients.get('PNC', 0) + service_clients.get('Newborn', 0):,}", 'Combined postnatal and newborn clients', '#2563EB'),
    ]

    narrative = []
    if selected_districts:
        narrative.append(f"District filter: {', '.join(selected_districts[:4])}{'...' if len(selected_districts) > 4 else ''}")
    elif selected_facilities:
        narrative.append(f"Facility filter: {', '.join(selected_facilities[:3])}{'...' if len(selected_facilities) > 3 else ''}")
    else:
        narrative.append('Showing the unified MNH MoH view across the current user scope.')
    narrative.append('This view combines Maternal Health and Newborn MNID indicators into one MoH dashboard.')

    section_nodes = []
    for section_name, _cats in _SECTION_ORDER:
        section_items = sections.get(section_name, [])
        if section_name == 'Overview':
            overview_cards = [
                _indicator_card(indicator)
                for indicator in overview_indicators[:6]
            ]
            if overview_cards:
                section_nodes.append(_section_shell(section_name, 'High-level service activity and outcomes for the selected reporting window.', overview_cards))
            continue
        if section_name == 'Data Quality':
            if readiness_indicators:
                dq_items = [item for item in readiness_indicators if 'data' in str(item.get('label', '')).lower() or 'completeness' in str(item.get('label', '')).lower()]
                if dq_items:
                    section_nodes.append(_section_shell(section_name, 'Documentation quality and timeliness signals from the existing MNID metadata.', [_indicator_card(item) for item in dq_items]))
            continue
        if not section_items:
            continue
        section_nodes.append(_section_shell(section_name, f'{len(section_items)} indicator(s) aligned to the unified MoH reporting experience.', [_indicator_card(item) for item in section_items]))

    readiness_cards = [
        _indicator_card(item)
        for item in readiness_indicators
        if 'data' not in str(item.get('label', '')).lower() and 'completeness' not in str(item.get('label', '')).lower()
    ]
    maternal_deaths = _find_indicator_value(overview_indicators + tracked_indicators, ('Maternal Deaths',))
    neonatal_deaths = _find_indicator_value(overview_indicators + tracked_indicators, ('Newborn Deaths', 'Neonatal Deaths'))
    stillbirths = _find_indicator_value(overview_indicators + tracked_indicators, ('Stillbirths',))
    live_births = _find_indicator_value(overview_indicators + tracked_indicators, ('Live Births',))
    total_births = live_births + stillbirths
    complication_burden = (
        _find_indicator_value(overview_indicators + tracked_indicators, ('ANC Complications',)) +
        _find_indicator_value(overview_indicators + tracked_indicators, ('Labour Complications',)) +
        _find_indicator_value(overview_indicators + tracked_indicators, ('Mother Complications',)) +
        _find_indicator_value(overview_indicators + tracked_indicators, ('Newborn Complications', 'Neonatal Complications at Birth'))
    )
    maternal_rate = round((maternal_deaths / live_births) * 100000, 1) if live_births else 0.0
    neonatal_rate = round((neonatal_deaths / live_births) * 1000, 1) if live_births else 0.0
    stillbirth_rate = round((stillbirths / total_births) * 1000, 1) if total_births else 0.0
    section_names = [name for name, _cats in _SECTION_ORDER if any(_SECTION_IDS.get(name) == node.id for node in section_nodes)]
    if readiness_cards and 'Operational Readiness and Signal Functions' not in section_names:
        section_names.append('Operational Readiness and Signal Functions')

    return html.Div(
        className='mnid-main',
        style={'padding': '18px', 'background': 'linear-gradient(180deg, #F8FAFC 0%, #F3F7FB 100%)'},
        children=[
            _summary_header(_period_label(start_date, end_date), active_districts, active_facilities, completeness),
            _meta_bar(_period_label(start_date, end_date), active_districts, active_facilities, completeness),
            html.Div(
                style={
                    'padding': '24px',
                    'borderRadius': '24px',
                    'background': 'linear-gradient(135deg, #FFFFFF 0%, #F6FBF8 55%, #F4F8FD 100%)',
                    'border': f'1px solid {BORDER}',
                    'marginBottom': '20px',
                    'boxShadow': '0 18px 40px rgba(15, 23, 42, 0.05)',
                },
                children=[
                    html.Div('MNH-MoH', style={'fontSize': '12px', 'fontWeight': 800, 'letterSpacing': '0.08em', 'textTransform': 'uppercase', 'color': '#166534'}),
                    html.Div('Maternal and Neonatal Outcomes Dashboard', style={'fontSize': '28px', 'fontWeight': 800, 'color': TEXT, 'marginTop': '8px'}),
                    html.Div('Malawi national overview · Maternal and newborn evidence for action · Decision support', style={'fontSize': '13px', 'color': '#94A3B8', 'marginTop': '4px'}),
                    html.Div(
                        style={'display': 'flex', 'gap': '8px', 'flexWrap': 'wrap', 'marginTop': '12px', 'marginBottom': '18px'},
                        children=[
                            _badge('Live', '#166534', '#E8F7EF'),
                            _badge(_period_label(start_date, end_date), '#475569', '#FFFFFF'),
                            _badge(f'{active_districts} districts · {active_facilities} facilities', '#475569', '#FFFFFF'),
                            _badge(f'Completeness {completeness:.1f}%', '#166534', '#ECFDF5'),
                        ],
                    ),
                    _priority_alert(maternal_deaths, neonatal_deaths, stillbirths, complication_burden),
                    html.Div(
                        style={
                            'display': 'grid',
                            'gridTemplateColumns': 'minmax(0, 1.35fr) minmax(280px, 0.85fr)',
                            'gap': '16px',
                            'alignItems': 'stretch',
                        },
                        children=[
                            html.Div(
                                children=[
                                    html.Div(
                                        style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'marginBottom': '8px'},
                                        children=[
                                            html.Div(style={'width': '4px', 'height': '18px', 'borderRadius': '999px', 'background': '#166534'}),
                                            html.Div('Country Summary — Current Reporting Period', style={'fontSize': '11px', 'fontWeight': 800, 'letterSpacing': '0.08em', 'textTransform': 'uppercase', 'color': '#6B7280'}),
                                        ],
                                    ),
                                    html.Div(
                                        hero_cards,
                                        style={
                                            'display': 'grid',
                                            'gridTemplateColumns': 'repeat(auto-fit, minmax(170px, 1fr))',
                                            'gap': '10px',
                                        },
                                    ),
                                ]
                            ),
                            _summary_rail(narrative, selected_districts, selected_facilities, service_clients, active_facilities, active_districts),
                        ],
                    ),
                ],
            ),
            _module_tabs(section_names),
            html.Div(
                style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'marginBottom': '12px'},
                children=[
                    html.Div(style={'width': '4px', 'height': '18px', 'borderRadius': '999px', 'background': '#166534'}),
                    html.Div('Mortality Snapshot — Immediate Attention Required', style={'fontSize': '11px', 'fontWeight': 800, 'letterSpacing': '0.08em', 'textTransform': 'uppercase', 'color': '#6B7280'}),
                ],
            ),
            html.Div(
                style={
                    'display': 'grid',
                    'gridTemplateColumns': 'repeat(auto-fit, minmax(260px, 1fr))',
                    'gap': '14px',
                    'marginBottom': '18px',
                },
                children=[
                    _mortality_card('Maternal deaths', maternal_deaths, 'MMR per 100,000 live births', maternal_rate, 'red', 'Recorded in selected reporting period.'),
                    _mortality_card('Neonatal deaths', neonatal_deaths, 'NMR per 1,000 live births', neonatal_rate, 'amber', 'Recorded in selected reporting period.'),
                    _mortality_card('Stillbirths', stillbirths, 'SBR per 1,000 total births', stillbirth_rate, 'purple', 'Recorded in selected reporting period.'),
                ],
            ),
            html.Div(
                style={
                    'display': 'grid',
                    'gridTemplateColumns': 'repeat(auto-fit, minmax(320px, 1fr))',
                    'gap': '14px',
                    'marginBottom': '20px',
                },
                children=[
                    _chart_block('Monthly service volumes', _service_volume_fig(working_df)),
                    _chart_block('Outcome counts in selected window', _outcome_mix_fig(overview_indicators + tracked_indicators)),
                ],
            ),
            html.Div(
                chart_items,
                style={
                    'display': 'grid',
                    'gridTemplateColumns': 'repeat(auto-fit, minmax(280px, 1fr))',
                    'gap': '14px',
                    'marginBottom': '20px',
                },
            ) if chart_items else None,
            *section_nodes,
            _section_shell(
                'Operational Readiness and Signal Functions',
                'Workforce, commodity, and signal-function proxies derived from the existing MNID metadata.',
                readiness_cards,
            ) if readiness_cards else None,
        ],
    )
