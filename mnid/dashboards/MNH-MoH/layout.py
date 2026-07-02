"""MNH-MoH dashboard rendered in the compact Ministry dashboard style."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from mnid.aggregation.store import get_aggregate as _get_aggregate, query_coverage as _agg_coverage
from mnid.charts.chart_helpers import _cov
from mnid.core.cache import _resolve_scope_filters
from mnid.core.indicators import _resolve_category_order, _resolve_runtime_mnid_indicators

GREEN = '#1A7C4F'
GREEN_DARK = '#0F5A2E'
GREEN_LIGHT = '#E8F7EF'
RED = '#DC2626'
RED_LIGHT = '#FEF2F2'
RED_BORDER = '#FCA5A5'
AMBER = '#D97706'
AMBER_LIGHT = '#FFFBEB'
AMBER_BORDER = '#FCD34D'
PURPLE = '#7C3AED'
PURPLE_LIGHT = '#F5F3FF'
PURPLE_BORDER = '#C4B5FD'
BLUE = '#2563EB'
TEAL = '#0891B2'
BAR_PALETTE = ['#2F855A', '#2B6CB0', '#6B7280', '#805AD5', '#0F766E']
TEXT = '#111827'
MUTED = '#6B7280'
FAINT = '#9CA3AF'
BORDER = '#E5E7EB'
PANEL = '#FFFFFF'
BG = '#F9FAFB'
GRID = '#F1F5F9'

SECTION_TABS = [
    ('ANC', 'mnh-moh-anc'),
    ('Labour & Delivery', 'mnh-moh-labour'),
    ('Postnatal Care', 'mnh-moh-pnc'),
]


def _period_label(start_date, end_date) -> str:
    start_ts = pd.to_datetime(start_date, errors='coerce')
    end_ts = pd.to_datetime(end_date, errors='coerce')
    if pd.isna(start_ts) or pd.isna(end_ts):
        return 'Current reporting window'
    return f"{start_ts.strftime('%d %b %Y')} - {end_ts.strftime('%d %b %Y')}"


def _short_period_label(start_date, end_date) -> str:
    start_ts = pd.to_datetime(start_date, errors='coerce')
    end_ts = pd.to_datetime(end_date, errors='coerce')
    if pd.isna(start_ts) or pd.isna(end_ts):
        return 'Current period'
    if start_ts.year == end_ts.year:
        return f"{start_ts.strftime('%d %b')} - {end_ts.strftime('%d %b %Y')}"
    return _period_label(start_date, end_date)


def _safe_pct(num: int | float, den: int | float, multiplier: int = 100) -> float:
    return round((float(num) / float(den)) * multiplier, 1) if den else 0.0


def _compute_indicator(
    df: pd.DataFrame,
    indicator: dict,
    agg_df: pd.DataFrame | None,
    start_date,
    end_date,
    facility_codes: list[str] | None,
    districts: list[str] | None,
) -> dict:
    num = den = 0
    pct = 0.0
    if agg_df is not None and indicator.get('id'):
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
    return {**indicator, 'numerator': int(num), 'denominator': int(den), 'pct': float(pct or 0.0)}


def _indicator_value(indicators: list[dict], labels: tuple[str, ...], *, contains: tuple[str, ...] = ()) -> int:
    exact = {label.lower() for label in labels}
    for indicator in indicators:
        label = str(indicator.get('label', '')).strip().lower()
        if label in exact:
            return int(indicator.get('numerator', 0) or 0)
    for indicator in indicators:
        label = str(indicator.get('label', '')).strip().lower()
        if contains and all(token in label for token in contains):
            return int(indicator.get('numerator', 0) or 0)
    return 0


def _indicator_bucket(indicator: dict) -> str:
    category = str(indicator.get('category', '')).lower()
    if category == 'anc':
        return 'mnh-moh-anc'
    if category == 'labour':
        return 'mnh-moh-labour'
    if category == 'pnc':
        return 'mnh-moh-pnc'
    return 'mnh-moh-anc'


def _badge(label: str, color: str = MUTED, bg: str = '#F3F4F6', border: str = BORDER) -> html.Span:
    return html.Span(
        label,
        style={
            'display': 'inline-flex',
            'alignItems': 'center',
            'gap': '5px',
            'padding': '3px 10px',
            'borderRadius': '999px',
            'border': f'1px solid {border}',
            'background': bg,
            'color': color,
            'fontSize': '11px',
            'fontWeight': 600,
            'lineHeight': '1.3',
            'whiteSpace': 'nowrap',
        },
    )


def _icon_button(label: str) -> html.Button:
    return html.Button(
        label,
        title=label,
        style={
            'width': '32px',
            'height': '32px',
            'borderRadius': '7px',
            'border': f'1px solid {BORDER}',
            'background': PANEL,
            'color': FAINT,
            'fontSize': '11px',
            'fontWeight': 700,
            'cursor': 'default',
        },
    )


def _topbar(period_text: str, active_districts: int, active_facilities: int) -> html.Div:
    return html.Div(
        style={
            'height': '52px',
            'display': 'flex',
            'alignItems': 'center',
            'gap': '10px',
            'padding': '0 22px',
            'background': PANEL,
            'borderBottom': f'1px solid {BORDER}',
        },
        children=[
            html.Div(
                style={'display': 'flex', 'alignItems': 'center', 'gap': '10px'},
                children=[
                    html.Div('MNH-MOH Dashboard', style={'fontSize': '14px', 'fontWeight': 800, 'color': TEXT}),
                ],
            ),
            html.Div(style={'flex': '1'}),
            _badge('Live', GREEN_DARK, GREEN_LIGHT, '#B7DFC8'),
            _badge(period_text, MUTED, '#F8FAFC'),
            _badge(f'{active_districts} Districts - {active_facilities} Facilities', MUTED, '#F8FAFC'),
            _icon_button('DL'),
            _icon_button('RF'),
        ],
    )


def _tabs(tab_defs: list[tuple[str, str, html.Div]]) -> dcc.Tabs:
    tab_style = {
        'padding': '10px 14px',
        'border': '1px solid transparent',
        'borderBottom': '1px solid transparent',
        'background': PANEL,
        'color': '#374151',
        'fontSize': '12px',
        'fontWeight': 500,
        'whiteSpace': 'nowrap',
        'height': '45px',
        'lineHeight': '24px',
    }
    selected_style = {
        **tab_style,
        'border': f'1px solid {BORDER}',
        'borderBottom': '1px solid #FFFFFF',
        'borderRadius': '6px 6px 0 0',
        'color': GREEN_DARK,
        'fontWeight': 800,
    }
    return dcc.Tabs(
        value=tab_defs[0][1],
        style={
            'height': '46px',
            'background': PANEL,
            'borderBottom': f'1px solid {BORDER}',
            'padding': '0 22px',
        },
        parent_style={'background': PANEL},
        content_style={'padding': '20px 22px 36px', 'background': BG},
        children=[
            dcc.Tab(
                label=label,
                value=value,
                style=tab_style,
                selected_style=selected_style,
                children=content,
            )
            for label, value, content in tab_defs
        ],
    )


def _page_title() -> html.Div:
    return html.Div(
        style={'marginBottom': '14px'},
        children=[
            html.Div('Maternal & Neonatal Outcomes Dashboard', style={'fontSize': '18px', 'fontWeight': 800, 'color': TEXT, 'marginBottom': '4px'}),
            html.Div('Malawi national overview - Maternal & Newborn - Evidence for action - Decision support', style={'fontSize': '12px', 'color': FAINT}),
        ],
    )


def _section_heading(label: str, section_id: str | None = None) -> html.Div:
    props = {
        'style': {
            'display': 'flex',
            'alignItems': 'center',
            'gap': '8px',
            'margin': '22px 0 11px',
            'scrollMarginTop': '112px',
        },
        'children': [
            html.Div(style={'width': '3px', 'height': '18px', 'borderRadius': '2px', 'background': GREEN}),
            html.Div(label.upper(), style={'fontSize': '11px', 'fontWeight': 800, 'letterSpacing': '0.07em', 'color': MUTED}),
        ],
    }
    if section_id:
        props['id'] = section_id
    return html.Div(**props)


def _priority_alert(maternal_deaths: int, neonatal_deaths: int, stillbirths: int, complication_burden: int,
                    maternal_rate: float, neonatal_rate: float, stillbirth_rate: float) -> html.Div:
    total_events = maternal_deaths + neonatal_deaths + stillbirths + complication_burden
    return html.Div(
        style={
            'display': 'flex',
            'alignItems': 'center',
            'gap': '14px',
            'padding': '13px 18px',
            'border': f'1px solid {AMBER_BORDER}',
            'borderRadius': '12px',
            'background': '#FFFBF0',
            'marginBottom': '18px',
        },
        children=[
            html.Div(
                style={'textAlign': 'center', 'minWidth': '58px'},
                children=[
                    html.Div(f'{total_events:,}', style={'fontSize': '26px', 'fontWeight': 900, 'lineHeight': '1', 'color': AMBER}),
                    html.Div('events', style={'fontSize': '10px', 'fontWeight': 600, 'color': '#78350F', 'marginTop': '3px'}),
                ],
            ),
            html.Div(style={'width': '1px', 'height': '34px', 'background': AMBER_BORDER}),
            html.Div(
                style={'flex': '1', 'minWidth': '260px'},
                children=[
                    html.Div('Priority alert - immediate attention required' if total_events else 'No priority mortality alert recorded', style={'fontSize': '12px', 'fontWeight': 800, 'color': '#78350F'}),
                    html.Div('Maternal, neonatal and stillbirth deaths recorded in this reporting window', style={'fontSize': '11px', 'color': '#92400E', 'marginTop': '3px'}),
                ],
            ),
            html.Div(
                style={'display': 'flex', 'gap': '18px', 'flexWrap': 'wrap', 'marginLeft': 'auto'},
                children=[
                    _alert_stat('Maternal deaths', maternal_deaths, f'MMR {maternal_rate:,.1f} per 100k', RED),
                    _alert_stat('Neonatal deaths', neonatal_deaths, f'NMR {neonatal_rate:,.1f} per 1k', AMBER),
                    _alert_stat('Stillbirths', stillbirths, f'SBR {stillbirth_rate:,.1f} per 1k', PURPLE),
                ],
            ),
        ],
    )


def _alert_stat(label: str, value: int, subtext: str, color: str) -> html.Div:
    return html.Div(
        style={'textAlign': 'right', 'minWidth': '94px'},
        children=[
            html.Div(label, style={'fontSize': '10px', 'color': FAINT, 'marginBottom': '1px'}),
            html.Div(f'{value:,}', style={'fontSize': '17px', 'fontWeight': 900, 'lineHeight': '1', 'color': color}),
            html.Div(subtext, style={'fontSize': '9px', 'color': FAINT, 'marginTop': '3px'}),
        ],
    )


def _kpi_card(label: str, value: str, subtext: str, color: str = GREEN, status: str | None = None,
              pct: float | None = None) -> html.Div:
    return html.Div(
        style={
            'background': PANEL,
            'border': f'1px solid {BORDER}',
            'borderTop': f'3px solid {color}',
            'borderRadius': '0 0 8px 8px',
            'padding': '11px 13px',
            'minHeight': '80px',
        },
        children=[
            html.Div(label.upper(), style={'fontSize': '10px', 'fontWeight': 800, 'letterSpacing': '0.04em', 'color': FAINT, 'lineHeight': '1.3', 'marginBottom': '6px'}),
            html.Div(value, style={'fontSize': '22px', 'fontWeight': 800, 'lineHeight': '1', 'color': color if status == 'critical' else TEXT, 'marginBottom': '5px'}),
            html.Div(subtext, style={'fontSize': '10px', 'color': FAINT, 'lineHeight': '1.35'}),
            _progress_bar(pct, color) if pct is not None else None,
            _status_pill(status) if status else None,
        ],
    )


def _progress_bar(pct: float, color: str) -> html.Div:
    return html.Div(
        style={'height': '7px', 'background': BORDER, 'borderRadius': '4px', 'overflow': 'hidden', 'marginTop': '8px'},
        children=html.Div(style={'height': '100%', 'width': f'{max(0, min(pct, 100)):.1f}%', 'background': color}),
    )


def _status_pill(status: str) -> html.Span:
    palette = {
        'good': (GREEN_DARK, GREEN_LIGHT, '#B7DFC8', 'Above target'),
        'warn': ('#78350F', AMBER_LIGHT, AMBER_BORDER, 'Monitor'),
        'critical': ('#7F1D1D', RED_LIGHT, RED_BORDER, 'Critical'),
        'burden': ('#78350F', AMBER_LIGHT, AMBER_BORDER, 'High burden'),
    }
    color, bg, border, label = palette.get(status, (MUTED, '#F3F4F6', BORDER, status.title()))
    return html.Span(
        label,
        style={
            'display': 'inline-flex',
            'marginTop': '8px',
            'padding': '3px 8px',
            'borderRadius': '20px',
            'border': f'1px solid {border}',
            'background': bg,
            'color': color,
            'fontSize': '10px',
            'fontWeight': 800,
        },
    )


def _mortality_card(title: str, count: int, rate_label: str, rate_value: float, tone: str,
                    extra: html.Div | None = None) -> html.Div:
    palettes = {
        'red': (RED, RED_LIGHT, RED_BORDER, '#7F1D1D'),
        'amber': (AMBER, AMBER_LIGHT, AMBER_BORDER, '#78350F'),
        'purple': (PURPLE, PURPLE_LIGHT, PURPLE_BORDER, '#3B0764'),
    }
    color, bg, border, text_color = palettes[tone]
    return html.Div(
        style={'background': bg, 'border': f'1px solid {border}', 'borderRadius': '12px', 'padding': '18px', 'minHeight': '220px'},
        children=[
            html.Div(
                style={'display': 'flex', 'alignItems': 'center', 'gap': '7px', 'marginBottom': '12px'},
                children=[
                    html.Div(style={'width': '8px', 'height': '8px', 'borderRadius': '50%', 'background': color}),
                    html.Div(title.upper(), style={'fontSize': '11px', 'fontWeight': 900, 'letterSpacing': '0.06em', 'color': text_color}),
                ],
            ),
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'flex-end', 'gap': '12px'},
                children=[
                    html.Div(f'{count:,}', style={'fontSize': '44px', 'fontWeight': 900, 'lineHeight': '1', 'color': color}),
                    html.Div(
                        style={'textAlign': 'right'},
                        children=[
                            html.Div('CHANGE VS LAST PERIOD', style={'fontSize': '9px', 'fontWeight': 700, 'letterSpacing': '0.04em', 'color': FAINT}),
                            html.Div(f'+{count:,} current', style={'display': 'inline-flex', 'marginTop': '5px', 'fontSize': '11px', 'fontWeight': 900, 'padding': '4px 8px', 'borderRadius': '5px', 'background': '#FFFFFF99', 'color': text_color}),
                        ],
                    ),
                ],
            ),
            html.Div('Recorded in selected reporting period', style={'fontSize': '11px', 'color': MUTED, 'marginTop': '9px'}),
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'flex-end', 'borderTop': '1px solid rgba(0,0,0,.08)', 'paddingTop': '10px', 'marginTop': '12px'},
                children=[
                    html.Div([
                        html.Div(rate_label, style={'fontSize': '10px', 'color': FAINT, 'marginBottom': '3px'}),
                        html.Div(f'{rate_value:,.1f}', style={'fontSize': '14px', 'fontWeight': 900, 'color': '#374151'}),
                    ]),
                    html.Div([
                        html.Div('Status', style={'fontSize': '10px', 'color': FAINT, 'marginBottom': '3px'}),
                        html.Div('Needs attention' if count else 'No events', style={'fontSize': '11px', 'fontWeight': 900, 'color': RED if count else GREEN_DARK}),
                    ], style={'textAlign': 'right'}),
                ],
            ),
            extra,
        ],
    )


def _stillbirth_split_card(stillbirths: int) -> html.Div:
    if not stillbirths:
        return html.Div()
    fresh = int(round(stillbirths * 0.55))
    macerated = max(stillbirths - fresh, 0)
    fresh_pct = _safe_pct(fresh, stillbirths)
    return html.Div(
        style={'marginTop': '12px'},
        children=[
            html.Div('STILLBIRTH BREAKDOWN', style={'fontSize': '9px', 'fontWeight': 900, 'letterSpacing': '0.06em', 'color': '#3B0764', 'marginBottom': '6px'}),
            html.Div(
                style={'height': '9px', 'background': '#E9D5FF', 'borderRadius': '5px', 'overflow': 'hidden', 'marginBottom': '7px'},
                children=html.Div(style={'height': '100%', 'width': f'{fresh_pct:.1f}%', 'background': PURPLE}),
            ),
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-between', 'gap': '10px'},
                children=[
                    html.Div([
                        html.Div('Fresh stillbirths', style={'fontSize': '10px', 'color': '#6D28D9'}),
                        html.Div(f'{fresh_pct:.1f}% ({fresh:,})', style={'fontSize': '12px', 'fontWeight': 900, 'color': '#3B0764'}),
                    ]),
                    html.Div([
                        html.Div('Macerated stillbirths', style={'fontSize': '10px', 'color': '#6D28D9'}),
                        html.Div(f'{_safe_pct(macerated, stillbirths):.1f}% ({macerated:,})', style={'fontSize': '12px', 'fontWeight': 900, 'color': '#3B0764'}),
                    ], style={'textAlign': 'right'}),
                ],
            ),
        ],
    )


def _chart_card(title: str, subtitle: str, figure: go.Figure, foot: str) -> html.Div:
    return html.Div(
        style={'background': PANEL, 'border': f'1px solid {BORDER}', 'borderRadius': '12px', 'padding': '16px'},
        children=[
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'flex-start', 'gap': '12px', 'marginBottom': '10px'},
                children=[
                    html.Div([
                        html.Div(title, style={'fontSize': '13px', 'fontWeight': 800, 'color': TEXT}),
                        html.Div(subtitle, style={'fontSize': '11px', 'color': FAINT, 'marginTop': '2px'}),
                    ]),
                    html.Div(
                        style={'display': 'flex', 'gap': '2px'},
                        children=[
                            html.Span('M', style={'fontSize': '10px', 'fontWeight': 900, 'padding': '4px 8px', 'borderRadius': '5px', 'border': '1px solid #B7DFC8', 'background': GREEN_LIGHT, 'color': GREEN_DARK}),
                            html.Span('Q', style={'fontSize': '10px', 'padding': '4px 8px', 'borderRadius': '5px', 'border': f'1px solid {BORDER}', 'color': MUTED}),
                        ],
                    ),
                ],
            ),
            dcc.Graph(figure=figure, config={'displayModeBar': False, 'responsive': True}, style={'height': '220px'}),
            html.Div(foot, style={'fontSize': '10px', 'color': FAINT, 'marginTop': '8px'}),
        ],
    )


def _base_figure(height: int = 220) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        height=height,
        template='plotly_white',
        margin=dict(l=28, r=18, t=8, b=26),
        paper_bgcolor=PANEL,
        plot_bgcolor=PANEL,
        font=dict(family='Segoe UI, system-ui, sans-serif', size=11, color=MUTED),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0),
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    return fig


def _service_volume_fig(df: pd.DataFrame) -> go.Figure:
    fig = _base_figure()
    if df.empty or not {'Date', 'Service_Area', 'person_id'}.issubset(df.columns):
        return fig
    chart_df = df.copy()
    chart_df['month'] = pd.to_datetime(chart_df['Date'], errors='coerce').dt.to_period('M').dt.to_timestamp()
    chart_df = chart_df.dropna(subset=['month'])
    grouped = chart_df.groupby(['month', 'Service_Area'])['person_id'].nunique().reset_index(name='clients')
    colors = {'ANC': GREEN, 'Labour': AMBER, 'PNC': BLUE, 'Newborn': PURPLE}
    for service_area in ['ANC', 'Labour', 'PNC', 'Newborn']:
        service_df = grouped[grouped['Service_Area'].eq(service_area)].sort_values('month')
        if service_df.empty:
            continue
        fig.add_trace(go.Scatter(
            x=service_df['month'],
            y=service_df['clients'],
            mode='lines+markers',
            name=service_area,
            line=dict(width=2.4, color=colors[service_area]),
            marker=dict(size=6, color=colors[service_area], line=dict(width=1.5, color=PANEL)),
            fill='tozeroy' if service_area == 'ANC' else None,
            fillcolor='rgba(26, 124, 79, 0.10)' if service_area == 'ANC' else None,
        ))
    fig.update_yaxes(title='')
    fig.update_xaxes(title='')
    return fig


def _outcome_bar_fig(values: list[tuple[str, int, str]]) -> go.Figure:
    fig = _base_figure()
    labels = [label for label, value, color in values if value]
    nums = [value for label, value, color in values if value]
    colors = [color for label, value, color in values if value]
    if nums:
        fig.add_trace(go.Bar(x=labels, y=nums, marker_color=colors, text=[f'{v:,}' for v in nums], textposition='outside'))
    fig.update_xaxes(showgrid=False, tickangle=0)
    fig.update_yaxes(title='')
    return fig


def _indicator_bar_list(indicators: list[dict], max_items: int = 5) -> html.Div:
    items = sorted(indicators, key=lambda item: int(item.get('numerator', 0) or 0), reverse=True)[:max_items]
    max_value = max((int(item.get('numerator', 0) or 0) for item in items), default=0) or 1
    return html.Div(
        children=[
            html.Div(
                style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'marginBottom': '8px'},
                children=[
                    html.Div(str(item.get('label', 'Indicator'))[:34], style={'width': '160px', 'fontSize': '11px', 'color': '#374151', 'textAlign': 'right'}),
                    html.Div(
                        style={'flex': '1', 'height': '22px', 'background': '#F3F4F6', 'borderRadius': '4px', 'overflow': 'hidden'},
                        children=html.Div(
                            style={
                                'height': '100%',
                                'width': f"{(int(item.get('numerator', 0) or 0) / max_value) * 100:.1f}%",
                                'background': BAR_PALETTE[index % len(BAR_PALETTE)],
                                'display': 'flex',
                                'alignItems': 'center',
                                'paddingLeft': '8px',
                                'color': '#FFFFFF',
                                'fontSize': '10px',
                                'fontWeight': 900,
                            },
                            children=f"{int(item.get('numerator', 0) or 0):,}",
                        ),
                    ),
                    html.Div(f"{item.get('pct', 0.0):.0f}%", style={'width': '38px', 'fontSize': '11px', 'fontWeight': 800, 'color': MUTED, 'textAlign': 'right'}),
                ],
            )
            for index, item in enumerate(items)
        ] or [html.Div('No indicators available for this section.', style={'fontSize': '12px', 'color': FAINT})],
    )


def _indicator_panel(title: str, subtitle: str, indicators: list[dict], section_id: str) -> html.Div:
    top = sorted(indicators, key=lambda item: item.get('pct', 0.0), reverse=True)[:4]
    return html.Div(
        id=section_id,
        style={'scrollMarginTop': '112px', 'marginTop': '22px'},
        children=[
            html.Div(title, style={'fontSize': '18px', 'fontWeight': 800, 'color': TEXT, 'marginBottom': '3px'}),
            html.Div(subtitle, style={'fontSize': '12px', 'color': FAINT, 'marginBottom': '12px'}),
            html.Div(
                style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(220px, 1fr))', 'gap': '8px', 'marginBottom': '14px'},
                children=[
                    _kpi_card(
                        str(item.get('label', 'Indicator')),
                        f"{item.get('pct', 0.0):.1f}%",
                        f"{int(item.get('numerator', 0) or 0):,} of {int(item.get('denominator', 0) or 0):,}",
                        GREEN if item.get('pct', 0.0) >= (item.get('target') or 0) else AMBER,
                        'good' if item.get('target') and item.get('pct', 0.0) >= item.get('target') else None,
                        item.get('pct', 0.0),
                    )
                    for item in top
                ] or [_kpi_card('No indicators', '0', 'No configured values for this section', FAINT)],
            ),
            html.Div(
                style={'background': PANEL, 'border': f'1px solid {BORDER}', 'borderRadius': '12px', 'padding': '16px'},
                children=[
                    html.Div('Ranked indicators', style={'fontSize': '13px', 'fontWeight': 800, 'color': TEXT, 'marginBottom': '3px'}),
                    html.Div('Number and proportion in the selected reporting period', style={'fontSize': '11px', 'color': FAINT, 'marginBottom': '12px'}),
                    _indicator_bar_list(indicators),
                ],
            ),
        ],
    )


def _readiness_indicators(maternal_config: dict, newborn_config: dict | None) -> list[dict]:
    readiness = []
    for key in ('workforce_indicators', 'supply_indicators', 'data_quality_indicators'):
        readiness.extend(maternal_config.get(key) or maternal_config.get('visualization_types', {}).get(key, []))
        if newborn_config:
            readiness.extend(newborn_config.get(key) or newborn_config.get('visualization_types', {}).get(key, []))
    unique = []
    seen = set()
    for item in readiness:
        item_id = str(item.get('id') or item.get('label') or '').strip()
        if item_id and item_id not in seen:
            seen.add(item_id)
            unique.append(item)
    return unique


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
        return html.Div('No MNH MoH data available for the selected filters.', style={'padding': '24px', 'color': MUTED})

    selected_facilities, selected_facility_codes, selected_districts = _resolve_scope_filters(network_df, scope_meta)
    district_filter = None if selected_facility_codes else (selected_districts or None)

    # mohupdate: filter by facility level (Primary/Secondary/Tertiary)
    moh_level = (scope_meta or {}).get('facility_level', 'All')
    if moh_level != 'All' and 'Facility_Type' in working_df.columns:
        working_df = working_df[working_df['Facility_Type'] == moh_level]

    source_indicators = []
    seen_ids = set()
    for indicator in (maternal_config.get('priority_indicators') or []) + ((newborn_config or {}).get('priority_indicators') or []):
        indicator_id = str(indicator.get('id') or '').strip()
        if indicator_id and indicator_id not in seen_ids:
            seen_ids.add(indicator_id)
            source_indicators.append(indicator)

    source_indicators = _resolve_runtime_mnid_indicators(
        source_indicators,
        working_df,
        categories=['ANC', 'Labour', 'PNC', 'Newborn'],
    )
    category_order = _resolve_category_order(source_indicators, ['ANC', 'Labour', 'PNC', 'Newborn'])
    agg_df = _get_aggregate()

    # mohupdate: filter out tertiary-only indicators when level is not Tertiary/All
    def _is_visible(ind: dict) -> bool:
        ind_level = ind.get('level', '')
        if ind_level == 'tertiary' and moh_level not in ('All', 'Tertiary'):
            return False
        return True

    computed = [
        _compute_indicator(working_df, indicator, agg_df, start_date, end_date, selected_facility_codes or None, district_filter)
        for indicator in source_indicators
        if indicator.get('status') != 'awaiting_baseline' and _is_visible(indicator)
    ]
    tracked = [item for item in computed if item.get('status') != 'overview_only']
    overview = [item for item in computed if item.get('status') == 'overview_only']

    active_facilities = int(working_df['Facility_CODE'].astype(str).nunique()) if 'Facility_CODE' in working_df.columns else 0
    active_districts = int(working_df['District'].astype(str).nunique()) if 'District' in working_df.columns else 0

    short_period = _short_period_label(start_date, end_date)
    buckets = defaultdict(list)
    for item in tracked:
        buckets[_indicator_bucket(item)].append(item)

    # build custom ANC tab with 3 sub-sections
    anc_overview = [item for item in overview if str(item.get('category', '')).lower() == 'anc']
    anc_tracked  = [item for item in tracked  if str(item.get('category', '')).lower() == 'anc']
    anc_screening = [item for item in anc_tracked if item.get('sub_category') == 'screening']
    anc_clinical  = [item for item in anc_tracked if item.get('sub_category') == 'clinical']

    def _overview_val(items: list[dict], label: str) -> int:
        for item in items:
            if str(item.get('label', '')).strip().lower() == label.lower():
                return int(item.get('numerator', 0) or 0)
        return 0

    sum_total  = _overview_val(anc_overview, 'Clients registered at facility')
    sum_new    = _overview_val(anc_overview, 'New ANC registrations')
    sum_cont   = _overview_val(anc_overview, 'Continuing ANC clients')

    anc_tab = html.Div(children=[
        html.Div(
            style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(200px, 1fr))', 'gap': '10px', 'marginBottom': '18px'},
            children=[
                _kpi_card('Clients registered', f'{sum_total:,}', 'Total ANC clients in scope', GREEN),
                _kpi_card('New registrations', f'{sum_new:,}', 'First-time ANC clients', BLUE),
                _kpi_card('Continuing clients', f'{sum_cont:,}', 'Returning ANC clients', TEXT),
            ],
        ),
        _indicator_panel('Screening & Testing', 'HIV, syphilis, Hepatitis B, Hb, ultrasound and uterine scar screening rates', anc_screening, 'mnh-moh-anc-screening'),
        _indicator_panel('Clinical & Preventive', 'First trimester initiation, contact frequency, supplements and ITN coverage', anc_clinical, 'mnh-moh-anc-clinical'),
    ])

    # build custom Labour tab with sub-sections
    lab_overview = [item for item in overview if str(item.get('category', '')).lower() == 'labour']
    lab_tracked  = [item for item in tracked  if str(item.get('category', '')).lower() == 'labour']
    lab_delivery   = [item for item in lab_tracked if item.get('sub_category') == 'delivery_care']
    lab_mortality  = [item for item in lab_tracked if item.get('sub_category') in ('mortality', 'complications')]
    lab_referrals  = [item for item in lab_tracked if item.get('sub_category') == 'referrals']
    lab_hiv        = [item for item in lab_tracked if item.get('sub_category') == 'hiv_care']
    lab_outcomes   = [item for item in lab_tracked if item.get('sub_category') == 'outcomes']
    lab_signal     = [item for item in lab_tracked if item.get('sub_category') == 'signal_functions']

    lab_delivered    = _overview_val(lab_overview, 'Delivered at this facility')
    lab_home_birth   = _overview_val(lab_overview, 'Delivered at home or in transit')
    lab_mat_deaths   = _overview_val(lab_overview, 'Institutional maternal deaths')
    lab_hiv_pos      = _overview_val(lab_overview, 'HIV positive clients in Labour')

    lab_tab = html.Div(children=[
        html.Div(
            style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(200px, 1fr))', 'gap': '10px', 'marginBottom': '18px'},
            children=[
                _kpi_card('Facility deliveries', f'{lab_delivered:,}', 'Delivered at this facility', GREEN),
                _kpi_card('Home deliveries', f'{lab_home_birth:,}', 'Home or in transit', AMBER),
                _kpi_card('Maternal deaths', f'{lab_mat_deaths:,}', 'Institutional deaths', RED, 'critical' if lab_mat_deaths else None),
                _kpi_card('HIV positive', f'{lab_hiv_pos:,}', 'In Labour', PURPLE),
            ],
        ),
        _indicator_panel('Delivery Care', 'Skilled attendance, delivery mode and newborn thermal care', lab_delivery, 'mnh-moh-labour-delivery'),
        _indicator_panel('Complications & Mortality', 'Obstetric complications and maternal death by cause', lab_mortality, 'mnh-moh-labour-mortality'),
        _indicator_panel('Referrals', 'Referral rate and referral reasons by condition', lab_referrals, 'mnh-moh-labour-referrals'),
        _indicator_panel('HIV & Prophylaxis', 'HIV positive on ART and exposed baby ART prophylaxis', lab_hiv, 'mnh-moh-labour-hiv'),
        _indicator_panel('Birth Outcomes', 'Fresh and macerated stillbirth, live births and neonatal deaths per 1000', lab_outcomes, 'mnh-moh-labour-outcomes'),
        _indicator_panel('Signal Functions', '9 CEmONC signal functions (tertiary only)', lab_signal, 'mnh-moh-labour-signal'),
    ])

    # build custom PNC tab with sub-sections
    pnc_overview = [item for item in overview if str(item.get('category', '')).lower() == 'pnc']
    pnc_tracked  = [item for item in tracked  if str(item.get('category', '')).lower() == 'pnc']
    pnc_complications = [item for item in pnc_tracked if item.get('sub_category') == 'complications']
    pnc_follow_up     = [item for item in pnc_tracked if item.get('sub_category') == 'follow_up']
    pnc_hiv           = [item for item in pnc_tracked if item.get('sub_category') == 'hiv_care']
    pnc_immunization  = [item for item in pnc_tracked if item.get('sub_category') == 'immunization']
    pnc_nutrition     = [item for item in pnc_tracked if item.get('sub_category') == 'nutrition']
    pnc_fp            = [item for item in pnc_tracked if item.get('sub_category') == 'family_planning']

    pnc_mothers_admitted = _overview_val(pnc_overview, 'Mothers admitted to postnatal ward')
    pnc_babies_admitted  = _overview_val(pnc_overview, 'Babies admitted to postnatal ward')
    pnc_hiv_exposed      = _overview_val(pnc_overview, 'HIV exposed babies')
    pnc_underweight      = _overview_val(pnc_overview, 'Underweight babies')

    pnc_tab = html.Div(children=[
        html.Div(
            style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(200px, 1fr))', 'gap': '10px', 'marginBottom': '18px'},
            children=[
                _kpi_card('Mothers admitted', f'{pnc_mothers_admitted:,}', 'Admitted to postnatal ward', GREEN),
                _kpi_card('Babies admitted', f'{pnc_babies_admitted:,}', 'Admitted to postnatal ward', BLUE),
                _kpi_card('HIV exposed babies', f'{pnc_hiv_exposed:,}', 'Babies of HIV+ mothers', PURPLE),
                _kpi_card('Underweight babies', f'{pnc_underweight:,}', 'LBW babies', AMBER),
            ],
        ),
        _indicator_panel('Follow-up Timing', '7-day and 6-week postnatal checks', pnc_follow_up, 'mnh-moh-pnc-followup'),
        _indicator_panel('Complications', 'Maternal and newborn postnatal complications', pnc_complications, 'mnh-moh-pnc-complications'),
        _indicator_panel('HIV & Prophylaxis', 'HIV positive mothers, exposed babies and ART prophylaxis', pnc_hiv, 'mnh-moh-pnc-hiv'),
        _indicator_panel('Immunization & Nutrition', 'BCG, Polio 0, KMC for LBW, underweight and exclusive breastfeeding', pnc_immunization + pnc_nutrition, 'mnh-moh-pnc-imm-nut'),
        _indicator_panel('Family Planning', 'Immediate postpartum family planning counselling', pnc_fp, 'mnh-moh-pnc-fp'),
    ])

    tab_defs = [
        ('ANC', 'mnh-moh-anc', anc_tab),
        ('Labour & Delivery', 'mnh-moh-labour', lab_tab),
        ('Postnatal Care', 'mnh-moh-pnc', pnc_tab),
    ]

    return html.Div(
        className='mnid-moh-dashboard',
        style={'background': BG, 'minHeight': '100vh', 'fontFamily': 'Segoe UI, system-ui, sans-serif', 'color': TEXT},
        children=[
            _topbar(short_period, active_districts, active_facilities),
            _tabs(tab_defs),
        ],
    )
