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
            'gap': '8px',
            'overflowX': 'auto',
            'paddingBottom': '4px',
            'marginBottom': '18px',
        },
        children=[
            html.A(
                section_name,
                href=f"#{_SECTION_IDS.get(section_name, '')}",
                style={
                    'display': 'inline-flex',
                    'alignItems': 'center',
                    'padding': '9px 14px',
                    'borderRadius': '12px',
                    'border': f'1px solid {BORDER}',
                    'background': '#FFFFFF',
                    'color': '#334155',
                    'fontSize': '12px',
                    'fontWeight': 700,
                    'textDecoration': 'none',
                    'whiteSpace': 'nowrap',
                    'boxShadow': '0 6px 18px rgba(15, 23, 42, 0.04)',
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
            'display': 'grid',
            'gridTemplateColumns': 'repeat(auto-fit, minmax(180px, 1fr))',
            'gap': '10px',
            'marginBottom': '18px',
        },
        children=[
            html.Div(
                style={
                    'padding': '12px 14px',
                    'borderRadius': '16px',
                    'background': '#FFFFFF',
                    'border': f'1px solid {BORDER}',
                },
                children=[
                    html.Div(label, style={'fontSize': '10px', 'fontWeight': 800, 'letterSpacing': '0.08em', 'textTransform': 'uppercase', 'color': DIM}),
                    html.Div(value, style={'fontSize': '14px', 'fontWeight': 800, 'color': TEXT, 'marginTop': '6px'}),
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
            'display': 'grid',
            'gridTemplateColumns': 'repeat(auto-fit, minmax(280px, 1fr))',
            'gap': '14px',
            'padding': '16px 18px',
            'borderRadius': '20px',
            'background': tone_bg,
            'border': f'1px solid {tone_border}',
            'marginBottom': '18px',
        },
        children=[
            html.Div([
                html.Div('Priority Alert', style={'fontSize': '11px', 'fontWeight': 800, 'letterSpacing': '0.08em', 'textTransform': 'uppercase', 'color': '#9A3412' if total_events else '#166534'}),
                html.Div(title, style={'fontSize': '20px', 'fontWeight': 900, 'color': TEXT, 'marginTop': '8px'}),
                html.Div(subtitle, style={'fontSize': '13px', 'lineHeight': '1.55', 'color': '#475569', 'marginTop': '6px'}),
            ]),
            html.Div(
                style={'display': 'grid', 'gridTemplateColumns': 'repeat(2, minmax(0, 1fr))', 'gap': '10px'},
                children=[
                    html.Div([
                        html.Div(label, style={'fontSize': '10px', 'fontWeight': 800, 'letterSpacing': '0.06em', 'textTransform': 'uppercase', 'color': DIM}),
                        html.Div(f'{value:,}', style={'fontSize': '24px', 'fontWeight': 900, 'color': color, 'marginTop': '8px'}),
                    ], style={'padding': '12px', 'borderRadius': '14px', 'background': '#FFFFFFB8', 'border': '1px solid rgba(255,255,255,0.6)'})
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
            'borderRadius': '18px',
            'padding': '18px',
            'background': '#FFFFFF',
            'boxShadow': '0 12px 30px rgba(15, 23, 42, 0.05)',
        },
        children=[
            html.Div(title, style={'fontSize': '12px', 'fontWeight': 700, 'color': DIM, 'textTransform': 'uppercase', 'letterSpacing': '0.06em'}),
            html.Div(value, style={'fontSize': '32px', 'fontWeight': 800, 'color': accent, 'marginTop': '8px'}),
            html.Div(subtext, style={'fontSize': '12px', 'color': DIM, 'marginTop': '6px'}),
        ],
    )


def _indicator_card(indicator: dict) -> html.Div:
    target = indicator.get('target')
    return html.Div(
        style={
            'border': f'1px solid {BORDER}',
            'borderRadius': '16px',
            'padding': '16px',
            'background': '#FFFFFF',
            'display': 'flex',
            'flexDirection': 'column',
            'gap': '10px',
        },
        children=[
            html.Div(
                style={'display': 'flex', 'justifyContent': 'space-between', 'gap': '12px', 'alignItems': 'flex-start'},
                children=[
                    html.Div([
                        html.Div(indicator.get('category', ''), style={'fontSize': '11px', 'fontWeight': 700, 'color': '#475569', 'textTransform': 'uppercase'}),
                        html.Div(indicator.get('label', ''), style={'fontSize': '14px', 'fontWeight': 700, 'color': TEXT, 'marginTop': '6px'}),
                    ]),
                    _status_badge(indicator.get('pct', 0.0), target, indicator.get('target_mode')),
                ],
            ),
            html.Div(f"{indicator.get('pct', 0.0):.1f}%", style={'fontSize': '28px', 'fontWeight': 800, 'color': '#0F172A'}),
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
                                'width': f"{max(0.0, min(indicator.get('pct', 0.0), 100.0)):.1f}%",
                                'background': '#16A34A' if indicator.get('pct', 0.0) >= (target or 0.0) else '#F59E0B',
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
        style={'marginTop': '28px', 'scrollMarginTop': '84px'},
        children=[
            html.Div(title, style={'fontSize': '22px', 'fontWeight': 800, 'color': TEXT}),
            html.Div(description, style={'fontSize': '13px', 'color': DIM, 'marginTop': '6px', 'marginBottom': '14px'}),
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
            'borderRadius': '18px',
            'padding': '12px',
            'background': '#FFFFFF',
        },
        children=[
            html.Div(title, style={'fontSize': '15px', 'fontWeight': 700, 'color': TEXT, 'padding': '4px 6px 0'}),
            dcc.Graph(figure=figure, config={'displayModeBar': False, 'responsive': True}, style={'height': '320px'}),
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
    complication_burden = (
        _find_indicator_value(overview_indicators + tracked_indicators, ('ANC Complications',)) +
        _find_indicator_value(overview_indicators + tracked_indicators, ('Labour Complications',)) +
        _find_indicator_value(overview_indicators + tracked_indicators, ('Mother Complications',)) +
        _find_indicator_value(overview_indicators + tracked_indicators, ('Newborn Complications', 'Neonatal Complications at Birth'))
    )
    section_names = [name for name, _cats in _SECTION_ORDER if any(_SECTION_IDS.get(name) == node.id for node in section_nodes)]
    if readiness_cards and 'Quality of Care / Signal Functions' not in section_names:
        section_names.append('Quality of Care / Signal Functions')

    return html.Div(
        className='mnid-main',
        children=[
            _meta_bar(_period_label(start_date, end_date), active_districts, active_facilities, completeness),
            html.Div(
                style={
                    'padding': '24px',
                    'borderRadius': '24px',
                    'background': 'linear-gradient(135deg, #F8FAFC 0%, #ECFDF5 55%, #EFF6FF 100%)',
                    'border': f'1px solid {BORDER}',
                    'marginBottom': '20px',
                },
                children=[
                    html.Div('MNH-MoH', style={'fontSize': '12px', 'fontWeight': 800, 'letterSpacing': '0.08em', 'textTransform': 'uppercase', 'color': '#166534'}),
                    html.Div('Unified Maternal and Newborn MoH Dashboard', style={'fontSize': '34px', 'fontWeight': 800, 'color': TEXT, 'marginTop': '8px'}),
                    html.Div(' '.join(narrative), style={'fontSize': '14px', 'color': DIM, 'marginTop': '8px', 'maxWidth': '980px'}),
                    html.Div(
                        hero_cards,
                        style={
                            'display': 'grid',
                            'gridTemplateColumns': 'repeat(auto-fit, minmax(220px, 1fr))',
                            'gap': '14px',
                            'marginTop': '18px',
                        },
                    ),
                ],
            ),
            _module_tabs(section_names),
            _priority_alert(maternal_deaths, neonatal_deaths, stillbirths, complication_burden),
            html.Div(
                style={
                    'display': 'grid',
                    'gridTemplateColumns': 'repeat(auto-fit, minmax(320px, 1fr))',
                    'gap': '14px',
                    'marginBottom': '20px',
                },
                children=[
                    _chart_block('Service volume trend', _service_volume_fig(working_df)),
                    _chart_block('Outcome mix', _outcome_mix_fig(overview_indicators + tracked_indicators)),
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
