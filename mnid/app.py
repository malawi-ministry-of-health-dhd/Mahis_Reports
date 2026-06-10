"""
MNID dashboard renderer.

This module builds the Maternal and Child Health dashboard layout,
calculates configured indicator coverage, and renders the main dashboard
sections such as trends, comparison views, heatmaps, and readiness panels.
"""
import dash_mantine_components as dmc
import json
import logging
import pandas as pd
pd.options.mode.chained_assignment = None
import plotly.graph_objects as go
from datetime import datetime
from pathlib import Path
from dash import html, dcc, clientside_callback, callback, callback_context, no_update, Input, Output, State, ALL
from dash.exceptions import PreventUpdate
from helpers.helpers import create_count_from_config
from mnid.constants import (
    OK_C, WARN_C, DANGER_C, INFO_C, MUTED, GRID_C, BG, BORDER, TEXT, DIM, FONT,
    CAT_PALETTES, HEATMAP_CS, FACILITY_DISTRICT as _FACILITY_DISTRICT,
    ALL_FACILITIES as _ALL_FACILITIES, ALL_DISTRICTS as _ALL_DISTRICTS,
    FACILITY_NAMES as _FACILITY_NAMES,
)
from mnid.data_utils import (
    prepare_mnid_dataframe as _prepare_mnid_dataframe,
    serialize_store_df as _serialize_store_df,
    deserialize_store_df as _deserialize_store_df,
    _remember_ui_payload, _restore_ui_dataframe,
    _MNID_UI_CACHE, _MNID_UI_DISK_CACHE,
)
from mnid.geo_utils import (
    load_malawi_district_geojson as _load_malawi_district_geojson,
    build_geo_reference as _build_geo_reference,
    derive_facility_positions as _derive_facility_positions,
)



from mnid.chart_helpers import (
    _CHART_LAYOUT, _TREND_SERIES_PALETTE, _TREND_ACCENT, _ANALYSIS_PALETTE,
    _CAT_LABELS, _CAT_ORDER,
    _warn_once, _moving_average_window, _moving_average_values,
    _filter_columns_missing, _cov, _monthly, _css, _CLR, _target_label,
    _on_target, _target_attainment_pct, _target_mode, _is_inverse_indicator,
    _display_pct, _axis_wrap, _infer_facility_type, _contrast_text,
    _value_counts, _flag_value_counts, _monthly_visits,
    _empty_card, _chart_card, _donut, _hbar, _line,
    _monthly_concept_rate, _monthly_concept_mix_fig, _concept_rate,
)
from mnid.indicators import (
    _resolve_category_order, _uses_program_based_mnid_schema,
    _program_based_priority_indicators, _program_based_overlay_fallbacks,
    _enrich_program_based_mnid_indicators, _resolve_runtime_mnid_indicators,
)
from mnid.heatmap import (
    _mask, _matrix_by_group, _matrix_monthly, _cov_color,
    _compute_heatmap_store, _build_facility_performance_heatmap_fig,
    _build_performance_attention_table, _build_heatmap_fig,
    _build_geo_heatmap_fig, _build_district_treemap, _build_malawi_panel,
)
from mnid.coverage import (
    _newborn_summary_card, _newborn_section_card,
    _first_available_value_counts, _newborn_tab_content,
    _facilities_requiring_attention, _coverage_heatmap_section,
    _ind_card, _phase_gauge_fig, _phase_gauge_row,
    _clinical_donuts_section, _coverage_phase_fig, _no_data_card,
    _coverage_charts_section, _acc_section, _chart_acc_section,
    _anc_charts, _labour_charts, _pnc_charts, _newborn_charts,
    _stat_row, _system_readiness, _compare_status_counts,
    _validate_indicator_configs, _build_compare_pie, _build_compare_bar,
    _build_compare_heatmap, _comparative_analysis_section,
)
from mnid.layout import (
    _TH, _hero_donut_card, _hero_donut_row, _priority_table,
    _district_gauge_fig, _build_district_gauge_row,
    _pph_cascade, _topbar, _sidebar, _alert_banner,
    _avg_ring, _count_bar, _kpi, _kpi_row, _section_anchor,
)
from mnid.executive_views import render_country_profile, render_operational_readiness

_MNID_UI_CACHE_MAX = 16
_MNID_UI_CACHE_TTL_SECONDS = 3600
_MNID_EXECUTIVE_CONTENT_CACHE = {}
_MNID_WARNED_MESSAGES = set()
_LOGGER = logging.getLogger(__name__)

_MNID_SCROLLSPY_CLIENTSIDE = """
function(_tick) {
    const sections = [
        '#mnid-summary',
        '#mnid-trends',
        '#mnid-performance',
        '#mnid-heatmap',
        '#mnid-comparative',
        '#mnid-analysis',
        '#mnid-readiness'
    ];

    let active = '#mnid-summary';
    const activationLine = 124;
    let bestPassed = null;
    let nextUpcoming = null;

    for (const selector of sections) {
        const el = document.querySelector(selector);
        if (!el) {
            continue;
        }

        const rect = el.getBoundingClientRect();
        const top = rect.top;

        if (top <= activationLine) {
            if (bestPassed === null || top > bestPassed.top) {
                bestPassed = { selector, top };
            }
        } else if (nextUpcoming === null || top < nextUpcoming.top) {
            nextUpcoming = { selector, top };
        }
    }

    if (bestPassed !== null) {
        active = bestPassed.selector;
    } else if (nextUpcoming !== null) {
        active = nextUpcoming.selector;
    }

    return active;
}
"""


def _load_mnid_report_config(report_name: str) -> dict | None:
    try:
        config_path = Path(__file__).resolve().parents[1] / 'data' / 'visualizations' / 'validated_dashboard.json'
        with open(config_path, 'r') as fh:
            dashboards = json.load(fh)
    except Exception:
        return None

    return next(
        (
            dashboard for dashboard in dashboards
            if dashboard.get('dashboard_type') == 'mnid'
            and dashboard.get('report_name') == report_name
        ),
        None,
    )


def _build_mnid_indicator_content(network_df: pd.DataFrame, config: dict,
                                  facility_code, start_date, end_date,
                                  scope_meta: dict | None = None) -> dict:
    facility_df = network_df
    if start_date and 'Date' in network_df.columns and not network_df.empty:
        try:
            s = pd.to_datetime(start_date)
            e = pd.to_datetime(end_date) if end_date else network_df['Date'].max()
            date_mask = (network_df['Date'] >= s) & (network_df['Date'] <= e)
            facility_df = network_df[date_mask]
        except Exception:
            facility_df = network_df

    selected_facilities = list(tuple(sorted((scope_meta or {}).get('selected_facilities') or [])))
    selected_districts = list(tuple(sorted((scope_meta or {}).get('selected_districts') or [])))
    if selected_facilities and 'Facility' in facility_df.columns:
        facility_df = facility_df[facility_df['Facility'].isin(selected_facilities)]
    elif selected_districts and 'District' in facility_df.columns:
        facility_df = facility_df[facility_df['District'].isin(selected_districts)]

    selected_program = (scope_meta or {}).get('mnid_categories')
    selected_program = selected_program[0] if selected_program else 'All'
    facility_df.attrs['mnid_program'] = selected_program
    network_df.attrs['mnid_program'] = selected_program
    if network_df.empty:
        network_df = facility_df

    vt = config.get('visualization_types', {})
    all_inds = config.get('priority_indicators') or vt.get('priority_indicators', [])
    supply_inds = config.get('supply_indicators') or vt.get('supply_indicators', [])
    wf_inds = config.get('workforce_indicators') or vt.get('workforce_indicators', [])
    dq_inds = config.get('data_quality_indicators') or vt.get('data_quality_indicators', [])
    period = f'{start_date} to {end_date}'
    period_note = (scope_meta or {}).get('data_period_note')

    requested_categories = (scope_meta or {}).get('mnid_categories')
    config_categories = config.get('mnid_categories')
    if config_categories:
        effective_categories = [c for c in (requested_categories or []) if c in config_categories] or config_categories
    else:
        effective_categories = requested_categories
    all_inds = _resolve_runtime_mnid_indicators(
        all_inds,
        facility_df,
        effective_categories,
    )
    _validate_indicator_configs(all_inds)
    category_order = _resolve_category_order(all_inds, effective_categories)
    if category_order:
        allowed = set(category_order)
        all_inds = [i for i in all_inds if i.get('category') in allowed]

    payload_key = f'{hash((len(network_df), tuple(network_df.columns.tolist()) if not network_df.empty else (), start_date, end_date, tuple(category_order)))}_{start_date}_{end_date}'

    tracked = [i for i in all_inds if i.get('status') == 'tracked']
    awaiting = [i for i in all_inds if i.get('status') == 'awaiting_baseline']
    default_cat = category_order[0] if category_order else 'ANC'

    if category_order == ['Newborn']:
        dashboard_title = 'Neonatal Care Dashboard'
        dashboard_subtitle = 'Program monitoring for admissions, outcomes, clinical interventions, coverage, and readiness.'
        dashboard_theme = 'newborn'
    elif set(category_order) == {'ANC', 'Labour', 'PNC'}:
        dashboard_title = 'Maternal Health Indicators'
        dashboard_subtitle = 'ANC, labour, and postnatal performance, comparison, coverage, and readiness.'
        dashboard_theme = 'default'
    else:
        dashboard_title = f"{config.get('report_name', 'Maternal and Child Health')} Indicators"
        dashboard_subtitle = 'Clean view of performance, comparison, coverage, and readiness.'
        dashboard_theme = 'default'

    if dashboard_theme == 'newborn' and not (supply_inds or wf_inds or dq_inds):
        _unavail = {'unique': 'person_id', 'variable1': 'concept_name', 'value1': '__mnid_unavailable__'}
        wf_inds = [
            {
                'label': 'SSNC competency assessed',
                'target_pct': 80,
                'numerator_filters': dict(_unavail),
                'denominator_filters': dict(_unavail),
            },
        ]
        supply_inds = [
            {
                'label': 'CPAP equipment available',
                'target_pct': 80,
                'numerator_filters': dict(_unavail),
                'denominator_filters': dict(_unavail),
            },
            {
                'label': 'Phototherapy unit available',
                'target_pct': 80,
                'numerator_filters': dict(_unavail),
                'denominator_filters': dict(_unavail),
            },
            {
                'label': 'Neonatal resuscitation equipment available',
                'target_pct': 80,
                'numerator_filters': dict(_unavail),
                'denominator_filters': dict(_unavail),
            },
        ]
        dq_inds = [
            {
                'label': 'Record completeness',
                'target_pct': 95,
                'numerator_filters': dict(_unavail),
                'denominator_filters': dict(_unavail),
            },
            {
                'label': 'Data entered within 7 days',
                'target_pct': 90,
                'numerator_filters': dict(_unavail),
                'denominator_filters': dict(_unavail),
            },
        ]
    hero_title = 'KEY NEONATAL INDICATORS' if dashboard_theme == 'newborn' else f'KEY {_CAT_LABELS.get(default_cat, str(default_cat or "Program")).upper()} INDICATORS'

    computed = []
    for ind in tracked:
        num, den, pct = _cov(facility_df, ind['numerator_filters'], ind['denominator_filters'])
        computed.append({
            **ind,
            'pct': pct,
            'numerator': num,
            'denominator': den,
            'attained_pct': _target_attainment_pct(pct, ind.get('target', 0), ind),
        })

    try:
        s = pd.to_datetime(start_date)
        e = pd.to_datetime(end_date) if end_date else network_df['Date'].max()
        window = max((e - s).days, 1)
        prev_end = s - pd.Timedelta(days=1)
        prev_start = prev_end - pd.Timedelta(days=window - 1)
        prev_df = network_df[
            (network_df['Date'] >= prev_start) & (network_df['Date'] <= prev_end)
        ] if 'Date' in network_df.columns and not network_df.empty else pd.DataFrame()
        if not prev_df.empty and selected_facilities and 'Facility' in prev_df.columns:
            prev_df = prev_df[prev_df['Facility'].isin(selected_facilities)]
        elif not prev_df.empty and selected_districts and 'District' in prev_df.columns:
            prev_df = prev_df[prev_df['District'].isin(selected_districts)]
    except Exception:
        prev_df = pd.DataFrame()

    for c in computed:
        if not prev_df.empty:
            try:
                _, _, prev_pct = _cov(prev_df, c['numerator_filters'], c['denominator_filters'])
                c['delta_pct'] = round(c['pct'] - prev_pct, 1)
            except Exception:
                c['delta_pct'] = None
        else:
            c['delta_pct'] = None

    below = [(c['label'], c['pct']) for c in computed if not _on_target(c['pct'], c['target'], c)]
    strong = [c['label'] for c in computed if _on_target(c['pct'], c['target'], c)]

    by_cat = {}
    for ind in all_inds:
        by_cat.setdefault(ind.get('category', 'Other'), []).append(ind)

    anc_charts = _anc_charts(facility_df)
    labour_charts = _labour_charts(facility_df)
    pnc_charts = _pnc_charts(facility_df)
    nb_charts = _newborn_charts(facility_df)

    analysis_acc = [
        _chart_acc_section('ch_anc', 'Antenatal Care', anc_charts) if anc_charts and 'ANC' in category_order else None,
        _chart_acc_section('ch_labour', 'Labour & Delivery', labour_charts) if labour_charts and 'Labour' in category_order else None,
        _chart_acc_section('ch_pnc', 'Postnatal Care', pnc_charts) if pnc_charts and 'PNC' in category_order else None,
        _chart_acc_section('ch_nb', 'Neonatal Care', nb_charts) if nb_charts and 'Newborn' in category_order else None,
    ]
    analysis_acc = [a for a in analysis_acc if a]

    performance_div, heatmap_div = _coverage_heatmap_section(all_inds, facility_code, facility_df)
    comparative_div = _comparative_analysis_section(all_inds, facility_code, facility_df, payload_key=payload_key)

    def _sec_header(title, count=None, desc=None, eyebrow=None):
        return html.Div(className=f'mnid-section-header{" mnid-section-header-newborn" if dashboard_theme == "newborn" else ""}', children=[
            html.Div([
                html.Div(eyebrow, className='mnid-section-header-eyebrow') if eyebrow else None,
                html.Span(title, className='mnid-section-header-title'),
                html.Div(desc, className='mnid-section-header-desc') if desc else None,
            ]),
            html.Span(f'{count} indicators' if count else '', className='mnid-section-header-count'),
        ])

    total_analysis = sum(
        len(charts) for cat, charts in [
            ('ANC', anc_charts),
            ('Labour', labour_charts),
            ('PNC', pnc_charts),
            ('Newborn', nb_charts),
        ] if cat in category_order
    )

    indicator_content = html.Div(className=f'mnid-main{" mnid-main-newborn" if dashboard_theme == "newborn" else ""}', children=[
        _topbar(facility_code, period, len(tracked), len(awaiting), facility_df=facility_df, network_df=network_df, period_note=period_note, title=dashboard_title, subtitle=dashboard_subtitle, theme=dashboard_theme),
        _sidebar(facility_code, theme=dashboard_theme),
        _alert_banner(below, strong),

        _section_anchor('mnid-summary'),
        _sec_header(
            'Overview',
            desc='Neonatal program snapshot, priority indicator posture, and facility context.' if dashboard_theme == 'newborn' else f'{len(tracked)} available - {len(awaiting)} awaiting',
            eyebrow='Overview' if dashboard_theme == 'newborn' else None,
        ),
        _kpi_row(computed),
        _hero_donut_row(computed, preferred_cat=default_cat, section_title=hero_title),
        _priority_table(computed),

        _section_anchor('mnid-trends'),
        _sec_header(
            'Run Charts',
            desc='Monthly trends for neonatal admissions and outcome-related indicators, with target references where applicable.' if dashboard_theme == 'newborn' else '12-month rolling - dotted line = target',
            eyebrow='Trends' if dashboard_theme == 'newborn' else None,
        ),
        _trend_switcher(facility_df, all_inds, scope_meta=scope_meta, payload_key=payload_key),

        _section_anchor('mnid-performance'),
        _sec_header(
            'District Performance' if dashboard_theme == 'newborn' else 'Facility Performance',
            desc='How this newborn service compares across district and facility peers.' if dashboard_theme == 'newborn' else 'District comparison heatmap for key performance indicators',
            eyebrow='Performance' if dashboard_theme == 'newborn' else None,
        ),
        performance_div,

        _section_anchor('mnid-heatmap'),
        _sec_header(
            'Geographic Coverage' if dashboard_theme == 'newborn' else 'Map View',
            desc='Geographic context for neonatal service delivery and district-level performance.' if dashboard_theme == 'newborn' else 'Geographic coverage map and district/facility context',
            eyebrow='Map' if dashboard_theme == 'newborn' else None,
        ),
        heatmap_div,

        _section_anchor('mnid-comparative'),
        _sec_header(
            'Facility Comparison' if dashboard_theme == 'newborn' else 'Facility & District Comparison',
            desc='Facility and district comparison for neonatal indicators.' if dashboard_theme == 'newborn' else 'Cross-facility and district indicator benchmarking',
            eyebrow='Comparison' if dashboard_theme == 'newborn' else None,
        ),
        comparative_div,

        _section_anchor('mnid-analysis'),
        _sec_header(
            'Clinical Interventions' if dashboard_theme == 'newborn' else 'Clinical Analysis',
            None if dashboard_theme == 'newborn' else total_analysis,
            desc='Clinical intervention, thermal support, respiratory support, and complication views.' if dashboard_theme == 'newborn' else 'Care-phase deep-dives',
            eyebrow='Clinical View' if dashboard_theme == 'newborn' else None,
        ),
        dmc.Accordion(
            multiple=True,
            value=[a.value for a in analysis_acc],
            variant='separated', radius='md', mb='md',
            children=analysis_acc,
            styles={
                'item': {'backgroundColor': BG, 'border': f'1px solid {BORDER}', 'borderRadius': '12px', 'marginBottom': '8px', 'boxShadow': '0 1px 3px rgba(0,0,0,0.04)'},
                'control': {'padding': '12px 16px'},
                'panel': {'padding': '0 16px 2px'},
            },
        ),
    ])

    indicator_content.children.extend([
        _section_anchor('mnid-readiness'),
        _sec_header(
            'Operational Readiness',
            desc='Devices, staffing, and data quality conditions that support neonatal care delivery.' if dashboard_theme == 'newborn' else 'Equipment - workforce competency - data quality',
            eyebrow='Readiness' if dashboard_theme == 'newborn' else None,
        ),
        _system_readiness(facility_df, supply_inds, wf_inds, dq_inds),
    ])

    return {
        'indicator_content': indicator_content,
        'facility_df': facility_df,
        'network_df': network_df,
        'supply_inds': supply_inds,
        'wf_inds': wf_inds,
        'dq_inds': dq_inds,
        'dashboard_theme': dashboard_theme,
    }


def clear_runtime_caches() -> None:
    _network_df_cache.clear()
    _MNID_UI_CACHE.clear()
    _MNID_EXECUTIVE_CONTENT_CACHE.clear()
    if _MNID_UI_DISK_CACHE is not None:
        try:
            _MNID_UI_DISK_CACHE.clear()
        except Exception:
            pass


def _cat_trend_fig(df: pd.DataFrame, cat_inds: list, cat: str, chart_type: str = 'line') -> go.Figure:
    palette = _TREND_SERIES_PALETTE
    fig = go.Figure()

    if not len(df) or not cat_inds:
        fig.add_annotation(text='No data available for this category',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG,
                          height=300, margin=dict(l=8, r=8, t=12, b=24))
        return fig

    # Vectorised monthly: one groupby per indicator across all months
    if 'Date' not in df.columns:
        return fig
    d2 = df
    d2['_m'] = pd.to_datetime(d2['Date']).dt.to_period('M')
    periods = sorted(d2['_m'].dropna().unique())[-12:]  # last 12 months

    n_by_m = {}; d_by_m = {}
    for ind in cat_inds:
        nm = _mask(d2, ind['numerator_filters'])
        dm = _mask(d2, ind['denominator_filters'])
        n_by_m[ind['id']] = d2[nm].groupby('_m')['person_id'].nunique().to_dict()
        d_by_m[ind['id']] = d2[dm].groupby('_m')['person_id'].nunique().to_dict()

    for j, ind in enumerate(cat_inds):
        c = palette[j % len(palette)]
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        xs, ys = [], []
        for p in periods:
            n = n_by_m[ind['id']].get(p, 0)
            d = d_by_m[ind['id']].get(p, 0)
            xs.append(pd.Period(p, 'M').to_timestamp().to_pydatetime())
            ys.append(round(n / d * 100, 1) if d > 0 else None)

        moving_average, _ = _moving_average_values(ys, 'monthly')

        has_data = any(y is not None for y in moving_average)
        if not has_data:
            if chart_type == 'bar':
                fig.add_trace(go.Bar(x=[], y=[], name=ind['label'], marker=dict(color=c), showlegend=True))
            else:
                fig.add_trace(go.Scatter(x=[], y=[], name=ind['label'], line=dict(color=c), showlegend=True))
            continue

        if chart_type == 'bar':
            clean_xs = [x for x, y in zip(xs, moving_average) if y is not None]
            clean_ys = [y for y in moving_average if y is not None]
            fig.add_trace(go.Bar(
                x=clean_xs, y=clean_ys, name=ind['label'],
                marker=dict(color=f'rgba({r},{g},{b},0.85)', line=dict(color=c, width=1)),
                hovertemplate=f'%{{x|%b %Y}}<br>{ind["label"]}: %{{y:.0f}}%<extra></extra>',
                offsetgroup=str(j),
            ))
        else:
            fig.add_trace(go.Scatter(
                x=xs, y=moving_average, name=ind['label'],
                mode='lines+markers',
                line=dict(color=c, width=2, shape='spline'),
                marker=dict(size=5, color=c, line=dict(color='#fff', width=1.25)),
                connectgaps=True,
                customdata=[[raw] for raw in ys],
                hovertemplate=f'%{{x|%b %Y}}<br>{ind["label"]} Moving Avg: %{{y:.1f}}%<br>Raw Coverage: %{{customdata[0]:.1f}}%<extra></extra>',
            ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        height=300,
        margin=dict(l=8, r=8, t=12, b=24),
        barmode='group' if chart_type == 'bar' else None,
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickformat='%b %y', tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED), range=[0, 105],
                   title=dict(text='Coverage %', font=dict(size=10, color=MUTED))),
        legend=dict(font=dict(size=10, color=DIM), bgcolor='rgba(0,0,0,0)',
                    orientation='v', x=1.01, y=1, xanchor='left', yanchor='top'),
        hovermode='closest' if chart_type == 'bar' else 'x unified',
    )
    return fig


@callback(
    Output('mnid-run-charts-container', 'children'),
    Output('mnid-trend-active-cat', 'data'),
    Output({'type': 'trend-cat-btn', 'index': ALL}, 'className'),
    Output('mnid-trend-location', 'options'),
    Output('mnid-trend-ind-filter', 'options'),
    Output('mnid-trend-ind-filter', 'value'),
    Input({'type': 'trend-cat-btn', 'index': ALL}, 'n_clicks'),
    Input('mnid-trend-location', 'value'),
    Input('mnid-trend-ind-filter', 'value'),
    State('mnid-trend-store', 'data'),
    State('mnid-trend-active-cat', 'data'),
    State('mnid-trend-cats-store', 'data'),
    prevent_initial_call=False,
)
def update_trend_chart(n_clicks_list, location, selected_inds, stored_trend, active_cat, cat_order):
    categories = cat_order or _CAT_ORDER
    cat = active_cat if active_cat in categories else (categories[0] if categories else 'ANC')

    ctx = callback_context
    triggered_prop = ctx.triggered[0]['prop_id'] if ctx and ctx.triggered else None
    cat_changed = False
    if triggered_prop and 'trend-cat-btn' in triggered_prop:
        try:
            next_cat = json.loads(triggered_prop.split('.')[0]).get('index', cat)
            if next_cat in categories:
                cat = next_cat
                cat_changed = True
        except Exception:
            pass

    trend_payload = stored_trend or {}
    tracked = trend_payload.get('tracked', [])
    df = _restore_ui_dataframe(trend_payload.get('data_key'))
    scope_meta = trend_payload.get('scope_meta') or {}
    loc_options = trend_payload.get('loc_options') or [{'label': 'All locations', 'value': 'all'}]
    ind_opts_by_cat = trend_payload.get('ind_opts_by_cat') or {}
    ind_options = ind_opts_by_cat.get(cat, [])

    ind_value_out = None if cat_changed else no_update

    cards = _run_chart_cards(df, tracked, cat, location or 'all',
                             selected_inds if not cat_changed else None,
                             scope_meta)
    classes = ['mnid-filter-btn active' if c == cat else 'mnid-filter-btn' for c in categories]
    return cards, cat, classes, loc_options, ind_options, ind_value_out


def _location_options_for_df(df: pd.DataFrame, scope_meta: dict) -> list[dict]:
    level = str((scope_meta or {}).get('level') or '').strip().lower()
    opts = [{'label': 'All locations', 'value': 'all'}]
    if df is None or df.empty:
        return opts
    if level == 'facility' and 'Facility_CODE' in df.columns:
        for fc in sorted(df['Facility_CODE'].dropna().astype(str).unique()):
            opts.append({'label': _FACILITY_NAMES.get(fc, fc), 'value': fc})
    elif 'District' in df.columns and df['District'].dropna().nunique() > 1:
        for d in sorted(df['District'].dropna().astype(str).unique()):
            opts.append({'label': d, 'value': d})
    elif 'Facility_CODE' in df.columns:
        for fc in sorted(df['Facility_CODE'].dropna().astype(str).unique()):
            opts.append({'label': _FACILITY_NAMES.get(fc, fc), 'value': fc})
    return opts


def _indicator_run_fig(plot_df: pd.DataFrame, ind: dict, color: str,
                       periods: list, tickfmt: str, hfmt: str,
                       grain: str = 'monthly') -> go.Figure:
    """Single-indicator run chart figure for one card."""
    nm = _mask(plot_df, ind['numerator_filters'])
    dm = _mask(plot_df, ind['denominator_filters'])
    pid = 'person_id'

    xs, ys = [], []
    n_vals, d_vals = [], []
    for p in periods:
        pm = plot_df['_p'] == p
        n_val = int(plot_df.loc[pm & nm, pid].dropna().nunique()) if pid in plot_df.columns else int((pm & nm).sum())
        d_val = int(plot_df.loc[pm & dm, pid].dropna().nunique()) if pid in plot_df.columns else int((pm & dm).sum())
        xs.append(p)
        ys.append(round(n_val / d_val * 100, 1) if d_val > 0 else None)
        n_vals.append(n_val)
        d_vals.append(d_val)

    smoothed, _ = _moving_average_values(ys, grain)
    valid_ys = [y for y in smoothed if y is not None]
    fig = go.Figure()
    if not valid_ys:
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, height=200,
                          margin=dict(l=8, r=8, t=4, b=4),
                          annotations=[dict(text='No data for this period',
                                            xref='paper', yref='paper', x=0.5, y=0.5,
                                            showarrow=False, font=dict(size=11, color=MUTED))])
        return fig

    target = ind.get('target')
    if target is not None:
        fig.add_trace(go.Scatter(
            x=xs, y=[target] * len(xs), mode='lines',
            line=dict(color='#94A3B8', width=1.5, dash='dot'),
            showlegend=False,
            hovertemplate=f'Target: {target}%<extra></extra>',
        ))

    valid_pts = [(x, y, raw) for x, y, raw in zip(xs, smoothed, ys) if y is not None]
    kp_set, key_pts = set(), []
    for pt in [valid_pts[0], max(valid_pts, key=lambda p: p[1]), valid_pts[-1]]:
        if pt[0] not in kp_set:
            kp_set.add(pt[0])
            key_pts.append(pt)
    fig.add_trace(go.Scatter(
        x=[p[0] for p in key_pts], y=[p[1] for p in key_pts],
        mode='markers+text',
        text=[f'{p[1]:.0f}%' for p in key_pts],
        textposition='top center',
        textfont=dict(size=9, color='#374151'),
        marker=dict(size=7, color='#1e293b'),
        showlegend=False,
        hovertemplate=f'%{{x|{hfmt}}}: %{{y:.0f}}%<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=xs, y=smoothed, mode='lines+markers',
        line=dict(color=color, width=2.4, shape='linear'),
        marker=dict(size=5, color=color, line=dict(color='#fff', width=1.2)),
        connectgaps=False, showlegend=False,
        customdata=list(zip(n_vals, d_vals)),
        hovertemplate=(
            f'<b>%{{x|{hfmt}}}</b><br>'
            'Moving Avg: <b>%{y:.1f}%</b><br>'
            'Clients: %{customdata[0]} / %{customdata[1]}'
            '<extra></extra>'
        ),
    ))
    layout_annotations = []
    if target is not None:
        layout_annotations.append(dict(
            x=1.0, y=target / 112, xref='paper', yref='paper',
            text=f'<b>target {target:.0f}%</b>',
            showarrow=False, font=dict(size=9, color='#64748B'),
            xanchor='left', yanchor='middle',
        ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=10),
        height=200, margin=dict(l=6, r=80, t=6, b=24),
        showlegend=False,
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickformat=tickfmt, tickfont=dict(size=9, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=9, color=MUTED), ticksuffix='%', range=[0, 112]),
        annotations=layout_annotations,
    )
    return fig


def _run_chart_cards(df: pd.DataFrame, indicators: list, cat: str,
                     location: str | None = None,
                     selected_ids: list | None = None,
                     scope_meta: dict | None = None) -> list:
    tracked = [i for i in indicators if i.get('status') == 'tracked' and i.get('category') == cat]
    if selected_ids:
        id_set = set(selected_ids)
        tracked = [i for i in tracked if i.get('id') in id_set] or tracked
    if not tracked or df is None or df.empty:
        return [html.Div('No indicators configured for this category.',
                         style={'color': MUTED, 'fontSize': '13px', 'padding': '24px'})]

    plot_df = df.copy()
    if location and location != 'all':
        for col_name in ('Facility_CODE', 'District'):
            if col_name in df.columns:
                mask = df[col_name].astype(str) == str(location)
                if mask.any():
                    plot_df = df[mask].copy()
                    break

    dates = pd.to_datetime(plot_df['Date'], errors='coerce').dropna()
    if dates.empty:
        return [html.Div('No data for the selected location.',
                         style={'color': MUTED, 'fontSize': '13px', 'padding': '24px'})]

    span = max(int((dates.max() - dates.min()).days), 0)
    if span <= 45:
        tickfmt, hfmt, grain = '%d %b', '%d %b %Y', 'daily'
        plot_df['_p'] = dates.dt.floor('D')
    elif span <= 180:
        tickfmt, hfmt, grain = '%d %b', '%d %b %Y', 'weekly'
        plot_df['_p'] = dates.dt.to_period('W').apply(lambda p: p.start_time)
    else:
        tickfmt, hfmt, grain = '%b %y', '%b %Y', 'monthly'
        plot_df['_p'] = dates.dt.to_period('M').apply(lambda p: datetime(p.year, p.month, 1))

    periods = sorted(plot_df['_p'].dropna().unique())
    if not periods:
        return [html.Div('No time periods available.',
                         style={'color': MUTED, 'fontSize': '13px', 'padding': '24px'})]

    cat_colors = CAT_PALETTES.get(cat, _TREND_SERIES_PALETTE)
    cards = []
    for idx, ind in enumerate(tracked):
        color = cat_colors[idx % len(cat_colors)]
        fig = _indicator_run_fig(plot_df, ind, color, periods, tickfmt, hfmt, grain)
        target = ind.get('target')
        target_badge = None
        if target is not None:
            cls = _css(
                _cov(plot_df, ind['numerator_filters'], ind['denominator_filters'])[2],
                target, ind,
            )
            badge_colors = {'ok': ('#D1FAE5', '#065F46'), 'warn': ('#FEF3C7', '#92400E'), 'danger': ('#FEE2E2', '#991B1B')}
            bg, fg = badge_colors.get(cls, ('#F1F5F9', '#475569'))
            target_badge = html.Span(
                f'Target {target}%',
                style={'fontSize': '10px', 'fontWeight': '600', 'padding': '2px 7px',
                       'borderRadius': '999px', 'backgroundColor': bg, 'color': fg,
                       'marginLeft': '6px'},
            )
        card = html.Div(className='mnid-chart-card', children=[
            html.Div(style={'display': 'flex', 'alignItems': 'center',
                            'justifyContent': 'space-between', 'marginBottom': '2px'}, children=[
                html.Div(ind['label'], style={
                    'fontSize': '11px', 'fontWeight': '600', 'color': TEXT, 'lineHeight': '1.3',
                }),
                target_badge,
            ]),
            dcc.Graph(
                figure=fig,
                config={'displayModeBar': 'hover',
                        'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'],
                        'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                style={'height': '200px'},
            ),
        ])
        cards.append(card)
    return cards


def _trend_switcher(df: pd.DataFrame, indicators: list, categories: list | None = None,
                    default_cat: str | None = None,
                    scope_meta: dict | None = None,
                    payload_key: str | None = None) -> html.Div:
    tracked = [i for i in indicators if i.get('status') == 'tracked']
    cat_order = _resolve_category_order(tracked, categories)
    default_cat = default_cat if default_cat in cat_order else (cat_order[0] if cat_order else 'ANC')
    loc_options = _location_options_for_df(df, scope_meta or {})

    ind_opts_by_cat = {
        c: [{'label': i['label'], 'value': i['id']}
            for i in tracked if i.get('category') == c]
        for c in cat_order
    }
    default_ind_opts = ind_opts_by_cat.get(default_cat, [])

    default_cards = _run_chart_cards(df, tracked, default_cat, 'all', None, scope_meta)
    trend_store = {
        'tracked': tracked,
        'data_key': _remember_ui_payload('trend', df, stable_key=payload_key),
        'scope_meta': scope_meta or {},
        'loc_options': loc_options,
        'ind_opts_by_cat': ind_opts_by_cat,
    }

    return html.Div(className='mnid-card', style={'marginBottom': '12px'}, children=[
        html.Div(style={'display': 'flex', 'alignItems': 'center',
                        'justifyContent': 'space-between', 'marginBottom': '10px',
                        'gap': '12px', 'flexWrap': 'wrap'}, children=[
            html.Div('RUN CHARTS', className='mnid-section-lbl', style={'marginBottom': '0'}),
            html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'flexWrap': 'wrap'}, children=[
                html.Div(className='mnid-filter-row', children=[
                    html.Button(
                        _CAT_LABELS.get(c, c),
                        id={'type': 'trend-cat-btn', 'index': c},
                        className='mnid-filter-btn' + (' active' if c == default_cat else ''),
                        n_clicks=0,
                    )
                    for c in cat_order
                ]),
                dcc.Dropdown(
                    id='mnid-trend-ind-filter',
                    options=default_ind_opts,
                    value=None,
                    multi=True,
                    clearable=True,
                    placeholder='All indicators',
                    style={'minWidth': '200px', 'maxWidth': '300px', 'fontSize': '12px'},
                ),
                dcc.Dropdown(
                    id='mnid-trend-location',
                    options=loc_options,
                    value='all',
                    clearable=False,
                    searchable=True,
                    placeholder='All locations',
                    style={'minWidth': '150px', 'maxWidth': '210px', 'fontSize': '12px'},
                ),
            ]),
        ]),
        dcc.Store(id='mnid-trend-store', data=trend_store),
        dcc.Store(id='mnid-trend-active-cat', data=default_cat),
        dcc.Store(id='mnid-trend-cats-store', data=cat_order),
        html.Div(
            id='mnid-run-charts-container',
            className='mnid-chart-grid',
            children=default_cards,
        ),
    ])


def _encounter_slice(df: pd.DataFrame, regex: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    token = str(regex or '').upper()
    if 'Service_Area' in df.columns:
        if 'ANC' in token and 'LABOUR' not in token and 'DELIVERY' not in token:
            return df[df['Service_Area'].astype(str) == 'ANC']
        if 'LABOUR' in token or 'DELIVERY' in token or 'BIRTH' in token:
            return df[df['Service_Area'].astype(str) == 'Labour']
        if 'PNC' in token or 'POSTNATAL' in token:
            return df[df['Service_Area'].astype(str) == 'PNC']
        if 'NEONATAL' in token or 'NEWBORN' in token:
            return df[df['Service_Area'].astype(str) == 'Newborn']
    if 'Encounter' not in df.columns:
        return pd.DataFrame()
    enc = df['Encounter'].fillna('').astype(str)
    return df[enc.str.contains(regex, case=False, na=False)]


def _count_entities(df: pd.DataFrame, col: str) -> int:
    if df is None or df.empty or col not in df.columns:
        return 0
    return int(df[col].dropna().astype(str).nunique())


def _concept_count(df: pd.DataFrame, concept: str, values=None,
                   col: str = 'obs_value_coded', any_value: bool = False) -> int:
    if df is None or df.empty or 'concept_name' not in df.columns:
        return 0
    sub = df[df['concept_name'].fillna('').astype(str) == concept]
    if sub.empty:
        return 0

    target_col = col if col in sub.columns else None
    if values is not None:
        if not target_col:
            return 0
        wanted = {str(v).strip().lower() for v in values}
        series = sub[target_col].fillna('').astype(str).str.strip().str.lower()
        sub = sub[series.isin(wanted)]
    elif any_value:
        for candidate in [col, 'obs_value_coded', 'Value', 'ValueN', 'Value_Name']:
            if candidate in sub.columns:
                series = sub[candidate].fillna('').astype(str).str.strip()
                sub = sub[series.ne('')]
                break

    if sub.empty:
        return 0
    if 'person_id' in sub.columns:
        return int(sub['person_id'].dropna().astype(str).nunique())
    return int(len(sub))


def _service_table_payload(df: pd.DataFrame, scope_meta: dict | None = None) -> dict:
    scope_meta = scope_meta or {}

    def _service_entities(src: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
        if src is None or src.empty:
            return []
        if 'Facility_CODE' in src.columns:
            entities = []
            for fac_code, fac_df in src.groupby('Facility_CODE', dropna=True, sort=True):
                fac_df = fac_df
                fac_name = str(fac_code)
                if 'Facility' in fac_df.columns:
                    names = fac_df['Facility'].dropna().astype(str)
                    if not names.empty:
                        fac_name = names.mode().iloc[0]
                else:
                    fac_name = _FACILITY_NAMES.get(str(fac_code), str(fac_code))
                entities.append((fac_name, fac_df))
            return entities
        scope_value = str(scope_meta.get('value') or 'Current selection')
        return [(scope_value, src)]

    metric_specs = {
        'ANC': {
            'title': 'ANC Summary',
            'subtitle': 'Facility rows with ANC service indicators as columns.',
            'encounter': 'ANC',
            'metrics': [
                ('ANC records', lambda x: _count_entities(x, 'encounter_id')),
                ('Unique ANC clients', lambda x: _count_entities(x, 'person_id')),
                ('ANC visits', lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'ANC VISIT'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Obstetric history recorded', lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'OBSTETRIC HISTORY'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Gestational age method recorded', lambda x: _concept_count(x, 'Gestational age recorded', any_value=True)),
                ('Pregnancy planned responses', lambda x: _concept_count(x, 'Pregnancy planned', any_value=True)),
                ('Planned pregnancies', lambda x: _concept_count(x, 'Pregnancy planned', ['Yes'])),
                ('Danger signs captured', lambda x: _concept_count(x, 'Danger signs present', any_value=True)),
                ('Tetanus dose status recorded', lambda x: _concept_count(x, 'Number of tetanus doses', any_value=True)),
                ('2+ tetanus doses recorded', lambda x: _concept_count(x, 'Number of tetanus doses', ['two doses', 'three doses', 'four doses'], col='obs_value_coded')),
            ],
            'chart_specs': [
                {
                    'id': 'anc_pregnancy_planned',
                    'label': 'Pregnancy Planned',
                    'title': 'Pregnancy Planned Responses',
                    'total_metric': 'Pregnancy planned responses',
                    'segments': [
                        {'label': 'Planned pregnancies', 'metric': 'Planned pregnancies', 'color': '#0F766E'},
                    ],
                    'remainder_label': 'No / other response',
                    'remainder_color': '#94A3B8',
                },
                {
                    'id': 'anc_tetanus',
                    'label': 'Tetanus 2+',
                    'title': 'Tetanus Dose Coverage',
                    'total_metric': 'Unique ANC clients',
                    'segments': [
                        {'label': '2+ doses recorded', 'metric': '2+ tetanus doses recorded', 'color': '#0F766E'},
                    ],
                    'remainder_label': 'Below 2 doses / not recorded',
                    'remainder_color': '#94A3B8',
                },
                {
                    'id': 'anc_gestation',
                    'label': 'Gestation Method',
                    'title': 'Gestational Age Method Documentation',
                    'total_metric': 'Unique ANC clients',
                    'segments': [
                        {'label': 'Gestation method recorded', 'metric': 'Gestational age method recorded', 'color': '#7C3AED'},
                    ],
                    'remainder_label': 'Missing gestation method',
                    'remainder_color': '#CBD5E1',
                },
            ],
        },
        'Labour': {
            'title': 'Labour & Delivery Summary',
            'subtitle': 'Facility rows with labour and delivery indicators as columns.',
            'encounter': 'LABOUR|DELIVERY|BIRTH',
            'metrics': [
                ('Labour records', lambda x: _count_entities(x, 'encounter_id')),
                ('Unique mothers', lambda x: _count_entities(x, 'person_id')),
                ('Labour assessments', lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'LABOUR ASSESSMENT'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Labour visits', lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'Labour and delivery visit'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Delivery details recorded', lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'Delivery Details'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Place of delivery recorded', lambda x: _concept_count(x, 'Place of delivery', any_value=True)),
                ('This facility deliveries', lambda x: _concept_count(x, 'Place of delivery', ['This facility', 'this facility'])),
                ('Newborn complications recorded', lambda x: _concept_count(x, 'Newborn baby complications', any_value=True)),
                ('Vitamin K given', lambda x: _concept_count(x, 'Vitamin K given', ['Yes'])),
                ('Breastfeeding in first hour', lambda x: _concept_count(x, 'Breast feeding', ['Yes'])),
            ],
            'chart_specs': [
                {
                    'id': 'labour_delivery_location',
                    'label': 'Delivery Location',
                    'title': 'Place of Delivery',
                    'total_metric': 'Place of delivery recorded',
                    'segments': [
                        {'label': 'This facility', 'metric': 'This facility deliveries', 'color': '#0F766E'},
                    ],
                    'remainder_label': 'Other / not recorded',
                    'remainder_color': '#CBD5E1',
                },
                {
                    'id': 'labour_newborn_care',
                    'label': 'Immediate Newborn Care',
                    'title': 'Birth Interventions Documented',
                    'total_metric': 'Unique mothers',
                    'segments': [
                        {'label': 'Vitamin K given', 'metric': 'Vitamin K given', 'color': '#C2410C'},
                        {'label': 'Breastfeeding in first hour', 'metric': 'Breastfeeding in first hour', 'color': '#0F766E'},
                    ],
                    'remainder_label': 'Other / not documented',
                    'remainder_color': '#94A3B8',
                },
            ],
        },
        'Newborn': {
            'title': 'Newborn Summary',
            'subtitle': 'Facility rows with newborn care indicators as columns.',
            'encounter': 'NEONATAL',
            'metrics': [
                ('Neonatal records', lambda x: _count_entities(x, 'encounter_id')),
                ('Unique babies', lambda x: _count_entities(x, 'person_id')),
                ('Neonatal enrolment', lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'NEONATAL ENROLMENT'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Birth weight recorded', lambda x: _concept_count(x, 'Birth weight', any_value=True)),
                ('Gestation weeks recorded', lambda x: _concept_count(x, 'Gestation in weeks', any_value=True)),
                ('Vitamin K given', lambda x: _concept_count(x, 'Vitamin K given', ['Yes'])),
                ('Resuscitation recorded', lambda x: _concept_count(x, 'Neonatal resuscitation provided', any_value=True)),
                ('Active resuscitation', lambda x: _concept_count(x, 'Neonatal resuscitation provided', ['Yes', 'Stimulation only', 'Bag and mask'])),
                ('Thermal care recorded', lambda x: _concept_count(x, 'thermal care', any_value=True)),
                ('Mother status recorded', lambda x: _concept_count(x, 'Mother status', any_value=True)),
            ],
            'chart_specs': [
                {
                    'id': 'newborn_resuscitation',
                    'label': 'Resuscitation',
                    'title': 'Resuscitation Documentation',
                    'total_metric': 'Resuscitation recorded',
                    'segments': [
                        {'label': 'Active resuscitation', 'metric': 'Active resuscitation', 'color': '#0F766E'},
                    ],
                    'remainder_label': 'Other / no action recorded',
                    'remainder_color': '#CBD5E1',
                },
                {
                    'id': 'newborn_documentation',
                    'label': 'Documentation',
                    'title': 'Core Newborn Documentation',
                    'total_metric': 'Unique babies',
                    'segments': [
                        {'label': 'Birth weight recorded', 'metric': 'Birth weight recorded', 'color': '#7C3AED'},
                        {'label': 'Gestation weeks recorded', 'metric': 'Gestation weeks recorded', 'color': '#0891B2'},
                    ],
                    'remainder_label': 'Other / missing documentation',
                    'remainder_color': '#CBD5E1',
                },
            ],
        },
        'PNC': {
            'title': 'PNC Summary',
            'subtitle': 'Facility rows with postnatal care indicators as columns.',
            'encounter': 'PNC|POSTNATAL|POST.NATAL',
            'metrics': [
                ('PNC records', lambda x: _count_entities(x, 'encounter_id')),
                ('Unique mothers', lambda x: _count_entities(x, 'person_id')),
                ('PNC visits', lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'PNC VISIT'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Babies reviewed', lambda x: _concept_count(x, 'Status of baby', any_value=True)),
                ('Mother outcome recorded', lambda x: _concept_count(x, 'Status of the mother', any_value=True)),
                ('Mothers alive', lambda x: _concept_count(x, 'Status of the mother', ['Alive'])),
                ('Maternal deaths', lambda x: _concept_count(x, 'Status of the mother', ['Death', 'Died', 'Dead'])),
                ('Baby outcome recorded', lambda x: _concept_count(x, 'Status of baby', any_value=True)),
                ('Babies alive', lambda x: _concept_count(x, 'Status of baby', ['Alive'])),
                ('PNC within 48 hours', lambda x: _concept_count(x, 'Postnatal check period', ['Up to 48 hrs or before discharge'])),
                ('Immunisation recorded', lambda x: _concept_count(x, 'Immunisation given', any_value=True)),
                ('BCG given', lambda x: _concept_count(x, 'Immunisation given', ['BCG'])),
            ],
            'chart_specs': [
                {
                    'id': 'pnc_maternal_outcomes',
                    'label': 'Maternal Outcomes',
                    'title': 'Maternal PNC Outcomes',
                    'total_metric': 'Mother outcome recorded',
                    'segments': [
                        {'label': 'Mothers alive', 'metric': 'Mothers alive', 'color': '#0F766E'},
                        {'label': 'Maternal deaths', 'metric': 'Maternal deaths', 'color': '#DB2777'},
                    ],
                    'remainder_label': 'Other outcomes',
                    'remainder_color': '#CBD5E1',
                },
                {
                    'id': 'pnc_baby_outcomes',
                    'label': 'Baby Outcomes',
                    'title': 'Baby Outcomes During PNC',
                    'total_metric': 'Baby outcome recorded',
                    'segments': [
                        {'label': 'Babies alive', 'metric': 'Babies alive', 'color': '#0F766E'},
                        {'label': 'Babies reviewed', 'metric': 'Babies reviewed', 'color': '#2563EB'},
                    ],
                    'remainder_label': 'Other outcomes',
                    'remainder_color': '#CBD5E1',
                },
            ],
        },
    }

    payload = {}
    entities = _service_entities(df)
    for category, spec in metric_specs.items():
        section_rows = []
        for facility_name, fac_df in entities:
            slice_df = _encounter_slice(fac_df, spec['encounter'])
            values = [int(calc(slice_df)) for _label, calc in spec['metrics']]
            section_rows.append({'facility': facility_name, 'values': values})
        payload[category] = {
            'title': spec['title'],
            'subtitle': spec['subtitle'],
            'columns': [label for label, _calc in spec['metrics']],
            'rows': section_rows,
            'chart_specs': spec.get('chart_specs', []),
        }
    return payload


def _service_table_fig(section: dict) -> go.Figure:
    rows = section.get('rows', [])
    columns = section.get('columns', [])
    header_values = ['Facility Name'] + columns
    cell_values = [[row.get('facility', '') for row in rows]]
    for idx, _col in enumerate(columns):
        cell_values.append([f"{int(row.get('values', [])[idx]):,}" if idx < len(row.get('values', [])) else '0' for row in rows])
    fig = go.Figure(data=[go.Table(
        columnwidth=[0.24] + [0.12] * len(columns),
        header=dict(
            values=header_values,
            fill_color='#F8FAFC',
            line_color='#E2E8F0',
            align='left',
            font=dict(color='#0F172A', size=11, family=FONT),
            height=34,
        ),
        cells=dict(
            values=cell_values,
            fill_color='#FFFFFF',
            line_color='#E2E8F0',
            align=['left'] + ['right'] * len(columns),
            font=dict(
                color=[['#334155'] * len(rows)] + [['#0F172A'] * len(rows) for _ in columns],
                size=[11] + [12] * len(columns),
                family=FONT,
            ),
            height=38,
        ),
    )])
    fig.update_layout(
        title=dict(
            text=(
                f"<b>{section.get('title', 'Service Summary')}</b>"                 f"<br><span style='color:#94A3B8;font-size:11px;font-weight:500'>"                 f"{section.get('subtitle', '')}</span>"
            ),
            x=0,
            xanchor='left',
            font=dict(size=15, color=TEXT, family=FONT),
        ),
        margin=dict(l=0, r=0, t=56, b=0),
        height=max(340, 108 + (len(rows) * 38)),
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
    )
    return fig
def _service_stack_fig(section: dict, chart_id: str | None = None) -> go.Figure:
    rows = section.get('rows', [])
    chart_specs = section.get('chart_specs', []) or []
    fig = go.Figure()

    if not rows or not chart_specs:
        fig.add_annotation(
            text='No stacked metric available for this selection',
            xref='paper', yref='paper', x=0.5, y=0.5,
            showarrow=False, font=dict(size=12, color=MUTED),
        )
        fig.update_layout(
            paper_bgcolor='#FFFFFF',
            plot_bgcolor='#FFFFFF',
            height=320,
            margin=dict(l=8, r=8, t=32, b=8),
        )
        return fig

    spec = next((item for item in chart_specs if item.get('id') == chart_id), chart_specs[0])
    columns = section.get('columns', [])
    metric_index = {label: idx for idx, label in enumerate(columns)}
    facilities = [row.get('facility', '') for row in rows]

    remainder_vals = []
    seg_payloads = []
    for segment in spec.get('segments', []):
        seg_idx = metric_index.get(segment.get('metric'))
        vals = []
        for row in rows:
            row_vals = row.get('values', [])
            val = row_vals[seg_idx] if seg_idx is not None and seg_idx < len(row_vals) else 0
            vals.append(max(int(val or 0), 0))
        seg_payloads.append({**segment, 'values': vals})

    total_metric = spec.get('total_metric')
    total_idx = metric_index.get(total_metric) if total_metric else None
    if total_idx is not None:
        totals = []
        for row in rows:
            row_vals = row.get('values', [])
            total_val = row_vals[total_idx] if total_idx < len(row_vals) else 0
            totals.append(max(int(total_val or 0), 0))
    else:
        totals = [sum(segment['values'][row_idx] for segment in seg_payloads) for row_idx in range(len(rows))]

    for row_idx in range(len(rows)):
        subtotal = sum(segment['values'][row_idx] for segment in seg_payloads)
        remainder_vals.append(max(totals[row_idx] - subtotal, 0))

    for segment in seg_payloads:
        fig.add_trace(go.Bar(
            x=facilities,
            y=segment['values'],
            name=segment.get('label', ''),
            marker=dict(color=segment.get('color', INFO_C)),
            hovertemplate='%{x}<br>' + f"{segment.get('label', '')}: " + '%{y:,}<extra></extra>',
        ))

    if spec.get('remainder_label') and any(remainder_vals):
        fig.add_trace(go.Bar(
            x=facilities,
            y=remainder_vals,
            name=spec.get('remainder_label', 'Other'),
            marker=dict(color=spec.get('remainder_color', '#CBD5E1')),
            hovertemplate='%{x}<br>' + f"{spec.get('remainder_label', 'Other')}: " + '%{y:,}<extra></extra>',
        ))

    fig.update_layout(
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        title=dict(
            text=(
                f"<b>{spec.get('title', section.get('title', 'Service Snapshot'))}</b>"
                f"<br><span style='color:#94A3B8;font-size:11px;font-weight:500'>{section.get('subtitle', '')}</span>"
            ),
            x=0,
            xanchor='left',
            font=dict(size=15, color=TEXT, family=FONT),
        ),
        margin=dict(l=0, r=0, t=56, b=24),
        height=max(340, 280 + (18 if len(rows) > 4 else 0)),
        barmode='stack',
        legend=dict(orientation='h', x=0, y=1.12, xanchor='left',
                    font=dict(size=10, color=DIM)),
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED),
                   title=dict(text='Clients', font=dict(size=10, color=MUTED))),
    )
    return fig


def _service_stack_overview_fig(section: dict) -> go.Figure:
    chart_specs = section.get('chart_specs', []) or []
    rows = section.get('rows', [])
    fig = go.Figure()

    if not chart_specs or not rows:
        fig.add_annotation(
            text='No stacked indicators configured for this category',
            xref='paper', yref='paper', x=0.5, y=0.5,
            showarrow=False, font=dict(size=12, color=MUTED),
        )
        fig.update_layout(
            paper_bgcolor='#FFFFFF',
            plot_bgcolor='#FFFFFF',
            height=340,
            margin=dict(l=8, r=8, t=32, b=8),
        )
        return fig

    columns = section.get('columns', [])
    metric_index = {label: idx for idx, label in enumerate(columns)}
    labels = [_axis_wrap(spec.get('label', spec.get('title', 'Indicator')), width=22, max_lines=2) for spec in chart_specs]

    facilities = []
    if rows:
        facilities = [row.get('facility', '') for row in rows]
    subtitle = section.get('subtitle', '')
    if facilities:
        facility_text = ', '.join(str(name) for name in facilities[:3])
        if len(facilities) > 3:
            facility_text = f'{facility_text} +{len(facilities) - 3} more'
        subtitle = f'{subtitle} Aggregated across: {facility_text}.'.strip()

    spec_summaries = []
    for spec in chart_specs:
        segment_entries = []
        for segment in spec.get('segments', []):
            seg_idx = metric_index.get(segment.get('metric'))
            seg_total = 0
            if seg_idx is not None:
                for row in rows:
                    row_vals = row.get('values', [])
                    if seg_idx < len(row_vals):
                        seg_total += max(int(row_vals[seg_idx] or 0), 0)
            segment_entries.append({
                'label': segment.get('label', ''),
                'metric': segment.get('metric', ''),
                'color': segment.get('color', INFO_C),
                'value': seg_total,
            })

        total_metric = spec.get('total_metric')
        total_idx = metric_index.get(total_metric) if total_metric else None
        if total_idx is not None:
            total_val = 0
            for row in rows:
                row_vals = row.get('values', [])
                if total_idx < len(row_vals):
                    total_val += max(int(row_vals[total_idx] or 0), 0)
        else:
            total_val = sum(item['value'] for item in segment_entries)

        subtotal = sum(item['value'] for item in segment_entries)
        remainder_val = max(total_val - subtotal, 0)
        if spec.get('remainder_label'):
            segment_entries.append({
                'label': spec.get('remainder_label', 'Other'),
                'metric': total_metric or '',
                'color': spec.get('remainder_color', '#CBD5E1'),
                'value': remainder_val,
            })

        spec_summaries.append({
            'label': _axis_wrap(spec.get('label', spec.get('title', 'Indicator')), width=22, max_lines=2),
            'title': spec.get('title', spec.get('label', 'Indicator')),
            'total': total_val,
            'segments': [entry for entry in segment_entries if entry['value'] > 0],
        })

    max_segments = max((len(item['segments']) for item in spec_summaries), default=0)
    for seg_idx in range(max_segments):
        x_vals = []
        y_vals = []
        colors = []
        customdata = []
        names = []
        for summary in spec_summaries:
            if seg_idx >= len(summary['segments']):
                continue
            entry = summary['segments'][seg_idx]
            x_vals.append(entry['value'])
            y_vals.append(summary['label'])
            colors.append(entry['color'])
            names.append(entry['label'])
            customdata.append([
                summary['title'],
                entry['label'],
                summary['total'],
                entry['metric'],
            ])

        if x_vals:
            trace_name = next((name for name in names if name), f'Series {seg_idx + 1}')
            fig.add_trace(go.Bar(
                x=x_vals,
                y=y_vals,
                orientation='h',
                name=trace_name,
                marker=dict(color=colors),
                customdata=customdata,
                hovertemplate=(
                    '%{customdata[0]}<br>'
                    'Series: %{customdata[1]}<br>'
                    'Count: %{x:,}<br>'
                    'Reference total: %{customdata[2]:,}<extra></extra>'
                ),
            ))

    fig.update_layout(
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        title=dict(
            text=(
                f"<b>{section.get('title', 'Service Snapshot')} Indicator Comparison</b>"
                f"<br><span style='color:#94A3B8;font-size:11px;font-weight:500'>{subtitle}</span>"
            ),
            x=0,
            xanchor='left',
            font=dict(size=15, color=TEXT, family=FONT),
        ),
        margin=dict(l=0, r=0, t=62, b=72),
        height=max(352, 116 + len(spec_summaries) * 58),
        barmode='group',
        legend=dict(
            orientation='h',
            x=0,
            y=-0.18,
            xanchor='left',
            yanchor='top',
            font=dict(size=10, color=DIM),
            bgcolor='rgba(255,255,255,0.9)',
        ),
        xaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED),
                   title=dict(text='Clients', font=dict(size=10, color=MUTED))),
        yaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED), automargin=True),
    )
    return fig


def _service_snapshot_view(section: dict, view_mode: str) -> html.Div:
    if view_mode == 'chart':
        return html.Div(className='mnid-chart-card', children=[
            dcc.Graph(
                figure=_service_stack_overview_fig(section),
                config={
                    'displayModeBar': 'hover',
                    'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'],
                    'toImageButtonOptions': {'format': 'png', 'scale': 2},
                },
                style={'height': '360px'},
            ),
        ])
    return html.Div([
        dcc.Graph(
            id='mnid-service-table-graph',
            figure=_service_table_fig(section),
            className='mnid-service-table-graph',
            config={
                'displayModeBar': 'hover',
                'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'],
                'toImageButtonOptions': {'format': 'png', 'scale': 2},
            },
        ),
    ])


def _location_trend_fig(df: pd.DataFrame, cat_inds: list, cat: str,
                        chart_type: str = 'line',
                        scope_meta: dict | None = None) -> go.Figure:
    fig = go.Figure()
    if not len(df) or not cat_inds or 'Date' not in df.columns:
        fig.add_annotation(text='No trend data available for this selection',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG,
                          height=340, margin=dict(l=8, r=8, t=12, b=24))
        return fig

    d2 = df.copy()
    d2['Date'] = pd.to_datetime(d2['Date'], errors='coerce')
    d2 = d2.dropna(subset=['Date'])
    if d2.empty:
        fig.add_annotation(text='No dated records available for run chart view',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG,
                          height=340, margin=dict(l=8, r=8, t=12, b=24))
        return fig

    span_days = max(int((d2['Date'].max() - d2['Date'].min()).days), 0)
    if span_days <= 45:
        freq = 'D'
        tickformat = '%d %b'
        period_label = 'daily'
    elif span_days <= 180:
        freq = 'W-MON'
        tickformat = '%d %b'
        period_label = 'weekly'
    else:
        freq = 'M'
        tickformat = '%b %y'
        period_label = 'monthly'

    d2['_period'] = d2['Date'].dt.to_period(freq)
    periods = sorted(d2['_period'].dropna().unique())
    if not periods:
        fig.add_annotation(text='No time periods available for run chart view',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG,
                          height=340, margin=dict(l=8, r=8, t=12, b=24))
        return fig

    color_cycle = CAT_PALETTES.get(cat, _TREND_SERIES_PALETTE)
    active_inds = cat_inds[:2]

    for idx, ind in enumerate(active_inds):
        xs, ys = [], []
        for p in periods:
            period_df = d2[d2['_period'] == p]
            _, den, pct = _cov(period_df, ind['numerator_filters'], ind['denominator_filters'])
            xs.append(pd.Period(p, freq).to_timestamp().to_pydatetime())
            ys.append(_display_pct(pct) if den > 0 else None)
        moving_average, ma_window = _moving_average_values(ys, period_label)

        if not any(y is not None for y in moving_average):
            continue

        color = color_cycle[idx % len(color_cycle)]
        series_name = ind['label']
        clean_pairs = [(x, y, raw) for x, y, raw in zip(xs, moving_average, ys) if y is not None]
        clean_xs = [x for x, _, _ in clean_pairs]
        clean_ys = [y for _, y, _ in clean_pairs]
        clean_raw = [raw for _, _, raw in clean_pairs]

        if chart_type == 'bar':
            fig.add_trace(go.Bar(
                x=clean_xs,
                y=clean_ys,
                name=series_name,
                marker=dict(color=color, line=dict(color=color, width=1)),
                customdata=[[raw] for raw in clean_raw],
                hovertemplate=f'%{{x|%d %b %Y}}<br>{series_name} Moving Avg: %{{y:.1f}}%<br>Raw Coverage: %{{customdata[0]:.1f}}%<extra></extra>',
            ))
        else:
            fig.add_trace(go.Scatter(
                x=clean_xs,
                y=clean_ys,
                name=series_name,
                mode='lines+markers',
                line=dict(color=color, width=2.8, shape='linear'),
                marker=dict(size=6, color=color, line=dict(color='#fff', width=1.4)),
                connectgaps=False,
                customdata=[[raw] for raw in clean_raw],
                hovertemplate=f'%{{x|%d %b %Y}}<br>{series_name} Moving Avg: %{{y:.1f}}%<br>Raw Coverage: %{{customdata[0]:.1f}}%<extra></extra>',
            ))

            if idx == 0 and clean_xs:
                _tgt = ind.get('target')
                if _tgt is not None:
                    fig.add_trace(go.Scatter(
                        x=clean_xs, y=[_tgt] * len(clean_xs),
                        mode='lines',
                        line=dict(color='#A1A1AA', width=1.5, dash='dot'),
                        name=_target_label(ind),
                        showlegend=True,
                        hovertemplate=f'Target: {_tgt:.0f}%<extra></extra>',
                    ))

                key_points = []
                key_points.append((clean_xs[0], clean_ys[0], clean_raw[0]))
                if len(clean_xs) > 1:
                    key_points.append((clean_xs[-1], clean_ys[-1], clean_raw[-1]))
                peak_idx = clean_ys.index(max(clean_ys))
                peak_point = (clean_xs[peak_idx], clean_ys[peak_idx], clean_raw[peak_idx])
                if peak_point not in key_points:
                    key_points.append(peak_point)

                fig.add_trace(go.Scatter(
                    x=[x for x, _, _ in key_points],
                    y=[y for _, y, _ in key_points],
                    mode='markers+text',
                    text=[f'{y:.1f}' for _, y, _ in key_points],
                    textposition='top center',
                    marker=dict(size=8, color='black'),
                    showlegend=False,
                    customdata=[[raw] for _, _, raw in key_points],
                    hovertemplate=f'%{{x|%d %b %Y}}<br>{series_name} Moving Avg: %{{y:.1f}}%<br>Raw Coverage: %{{customdata[0]:.1f}}%<extra></extra>',
                ))

    if not fig.data:
        fig.add_annotation(text='No run chart points available for the selected indicator',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))

    chart_title = active_inds[0]['label'] if len(active_inds) == 1 else f'{_CAT_LABELS.get(cat, cat)} related indicators'
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        height=360,
        margin=dict(l=8, r=8, t=12, b=24),
        barmode='group' if chart_type == 'bar' else None,
        title=dict(text=f'{chart_title} ({period_label})', x=0.01, xanchor='left', font=dict(size=14, color=TEXT, family=FONT)),
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickformat=tickformat, tickfont=dict(size=10, color=MUTED),
                   title=dict(text='Date', font=dict(size=10, color=MUTED))),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED), range=[0, 105],
                   title=dict(text='Coverage %', font=dict(size=10, color=MUTED))),
        legend=dict(font=dict(size=10, color=DIM), bgcolor='rgba(0,0,0,0)',
                    orientation='h', x=0, y=1.05, xanchor='left', yanchor='bottom'),
        hovermode='closest' if chart_type == 'bar' else 'x unified',
    )
    return fig


@callback(
    Output('mnid-service-table-content', 'children'),
    Output('mnid-service-table-active-cat', 'data'),
    Output({'type': 'service-table-btn', 'index': ALL}, 'className'),
    Output('mnid-service-table-view-store', 'data'),
    Output('mnid-service-table-toggle', 'className'),
    Output('mnid-service-table-toggle-text', 'children'),
    Input('mnid-service-table-toggle', 'n_clicks'),
    Input({'type': 'service-table-btn', 'index': ALL}, 'n_clicks'),
    State('mnid-service-table-store', 'data'),
    State('mnid-service-table-active-cat', 'data'),
    State('mnid-service-table-cats-store', 'data'),
    State('mnid-service-table-view-store', 'data'),
    prevent_initial_call=False,
)
def update_service_table(toggle_clicks, n_clicks_list, stored_tables, active_cat, cat_order, view_mode):
    categories = cat_order or _CAT_ORDER
    cat = active_cat if active_cat in categories else (categories[0] if categories else 'ANC')
    view_mode = view_mode or 'table'
    ctx = callback_context
    if ctx and ctx.triggered:
        prop_id = ctx.triggered[0]['prop_id']
        if prop_id == 'mnid-service-table-toggle.n_clicks':
            view_mode = 'chart' if view_mode == 'table' else 'table'
        elif 'service-table-btn' in prop_id:
            try:
                next_cat = json.loads(prop_id.split('.')[0]).get('index', cat)
                if next_cat in categories:
                    cat = next_cat
            except Exception:
                pass

    tables = stored_tables or {}
    section = tables.get(cat) or next(iter(tables.values()), {'rows': []})
    classes = [
        'mnid-filter-btn active' if c == cat else 'mnid-filter-btn'
        for c in categories
    ]
    content = _service_snapshot_view(section, view_mode)
    toggle_class = 'mnid-trend-toggle is-bar' if view_mode == 'chart' else 'mnid-trend-toggle is-line'
    toggle_text = 'Chart' if view_mode == 'chart' else 'Table'
    return content, cat, classes, view_mode, toggle_class, toggle_text


def _service_table_switcher(df: pd.DataFrame, categories: list | None = None,
                            default_cat: str | None = None,
                            scope_meta: dict | None = None) -> html.Div:
    payload = _service_table_payload(df, scope_meta)
    cat_order = [c for c in _resolve_category_order([{'category': k} for k in payload.keys()], categories) if c in payload]
    default_cat = default_cat if default_cat in cat_order else (cat_order[0] if cat_order else 'ANC')
    default_section = payload.get(default_cat, {'rows': []})
    return html.Div(className='mnid-card', style={'marginBottom': '12px'}, children=[
        html.Div(style={'display': 'flex', 'alignItems': 'center',
                        'justifyContent': 'space-between', 'marginBottom': '8px', 'gap': '12px', 'flexWrap': 'wrap'}, children=[
            html.Div('SERVICE SNAPSHOT', className='mnid-section-lbl',
                     style={'marginBottom': '0'}),
            html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'flexWrap': 'wrap'}, children=[
                html.Button(
                    type='button',
                    id='mnid-service-table-toggle',
                    className='mnid-trend-toggle is-line',
                    n_clicks=0,
                    children=[
                        html.Span('Table', id='mnid-service-table-toggle-text', className='mnid-trend-toggle-text'),
                        html.Span(className='mnid-trend-toggle-thumb'),
                    ],
                ),
                html.Div(className='mnid-filter-row', children=[
                    html.Button(
                        _CAT_LABELS.get(c, c),
                        id={'type': 'service-table-btn', 'index': c},
                        className='mnid-filter-btn' + (' active' if c == default_cat else ''),
                        n_clicks=0,
                    )
                    for c in cat_order
                ]),
            ]),
        ]),
        dcc.Store(id='mnid-service-table-store', data=payload),
        dcc.Store(id='mnid-service-table-active-cat', data=default_cat),
        dcc.Store(id='mnid-service-table-cats-store', data=cat_order),
        dcc.Store(id='mnid-service-table-view-store', data='table'),
        html.Div(
            id='mnid-service-table-content',
            children=_service_snapshot_view(default_section, 'table'),
        ),
    ])


clientside_callback(
    _MNID_SCROLLSPY_CLIENTSIDE,
    Output('mnid-scrollspy-out', 'data'),
    Input('mnid-scrollspy-tick', 'n_intervals'),
)


@callback(
    Output({'type': 'mnid-nav-btn', 'index': ALL}, 'className'),
    Input('mnid-scrollspy-out', 'data'),
    State({'type': 'mnid-nav-btn', 'index': ALL}, 'id'),
    prevent_initial_call=False,
)
def sync_mnid_nav_active_state(active_hash, nav_ids):
    active_hash = active_hash or '#mnid-summary'
    classes = []
    for item in nav_ids or []:
        target = (item or {}).get('index')
        classes.append('mnid-nav-btn active' if target == active_hash else 'mnid-nav-btn')
    return classes

# # MNID module-level callback

@callback(
    Output('mnid-heatmap-graph', 'figure'),
    Output('mnid-heatmap-right', 'children'),
    Output('mnid-heatmap-district-wrap', 'style'),
    Input('mnid-heatmap-view',       'value'),
    Input('mnid-heatmap-district',   'value'),
    Input('mnid-heatmap-indicators', 'value'),
    State('mnid-heatmap-store',      'data'),
    prevent_initial_call=True,
)
def update_heatmap_view(view, district, sel_inds, stored):
    if not stored:
        return go.Figure(), html.Div(), {'display': 'none'}
    v = view or 'by_district'
    y = 'All years'
    fig   = _build_heatmap_fig(stored, v, y, district, sel_inds)
    panel = _build_malawi_panel(stored, v, y, district, sel_inds)
    district_style = {'display': 'block'} if v in ('by_district', 'district_facs') else {'display': 'none'}
    return fig, panel, district_style


@callback(
    Output('mnid-heatmap-district', 'value'),
    Input('mnid-malawi-treemap', 'clickData'),
    State('mnid-heatmap-store', 'data'),
    prevent_initial_call=True,
)
def sync_district_focus_from_treemap(click_data, stored):
    if not click_data or not click_data.get('points'):
        raise PreventUpdate

    point = click_data['points'][0]
    label = str(point.get('label', '')).strip()
    parent = str(point.get('parent', '')).strip()
    districts = set((stored or {}).get('all_districts', []))

    if label in districts:
        return label
    if parent in districts:
        return parent

    # Facility tiles can still be clicked; map facility label back to its district.
    clean_label = label.rstrip('*').strip()
    for fac_code, fac_name in _FACILITY_NAMES.items():
        if str(fac_name).strip() == clean_label:
            fac_dist = _FACILITY_DISTRICT.get(fac_code, '')
            if fac_dist in districts:
                return fac_dist

    raise PreventUpdate


@callback(
    Output('mnid-performance-heatmap-table', 'children'),
    Output('mnid-performance-aggregate', 'children'),
    Output('mnid-performance-attention', 'children'),
    Input('mnid-performance-indicators', 'value'),
    State('mnid-heatmap-store', 'data'),
    prevent_initial_call=True,
)
def update_performance_heatmap(sel_inds, stored):
    if not stored:
        return html.Div(), html.Div(), html.Div()
    table = _build_facility_performance_heatmap_fig(
        stored,
        'All years',
        sel_inds,
    )
    gauges = _build_district_gauge_row(stored, 'All years')
    attention = _build_performance_attention_table(
        stored,
        'All years',
        'All',
        'All',
        sel_inds,
    )
    return table, gauges, attention


_COMPARE_COLORS = [
    '#2563EB', '#0F766E', '#C2410C', '#7C3AED',
    '#DB2777', '#0891B2', '#4D7C0F', '#B45309',
    '#1D4ED8', '#BE185D',
]


@callback(
    Output('mnid-compare-bar-chart', 'figure'),
    Output('mnid-compare-entities', 'options'),
    Output('mnid-compare-entities', 'value'),
    Output('mnid-compare-indicators', 'options'),
    Output('mnid-compare-indicators', 'value'),
    Output('mnid-compare-chart-type-store', 'data'),
    Output('mnid-compare-chart-toggle', 'className'),
    Output('mnid-compare-chart-toggle-text', 'children'),
    Input('mnid-compare-mode', 'value'),
    Input('mnid-compare-entities', 'value'),
    Input('mnid-compare-time-grain', 'value'),
    Input('mnid-compare-indicators', 'value'),
    Input('mnid-compare-chart-toggle', 'n_clicks'),
    State('mnid-compare-store', 'data'),
    State('mnid-compare-chart-type-store', 'data'),
)
def update_compare_charts(mode, selected_entities, time_grain, selected_ind_ids, toggle_clicks, stored, chart_type):
    mode = mode or 'facility'
    time_grain = time_grain or 'weekly'
    chart_type = chart_type or 'line'
    ctx = callback_context
    user_changed_indicators = (
        ctx and ctx.triggered and
        ctx.triggered[0]['prop_id'] == 'mnid-compare-indicators.value'
    )
    if ctx and ctx.triggered and ctx.triggered[0]['prop_id'] == 'mnid-compare-chart-toggle.n_clicks':
        chart_type = 'line' if chart_type == 'bar' else 'bar'
    store_payload = stored or {}
    tracked = store_payload.get('tracked', [])
    mch_full = _restore_ui_dataframe(store_payload.get('data_key'))
    facility_options = store_payload.get('facility_options', [])
    district_options = store_payload.get('district_options', [])
    current_fac = store_payload.get('current_fac', '')
    current_dist = store_payload.get('current_dist', '')

    ind_options = [{'label': i['label'], 'value': i['id']} for i in tracked]
    valid_ind_ids = {opt['value'] for opt in ind_options}
    selected_ind_ids = [iid for iid in (selected_ind_ids or []) if iid in valid_ind_ids][:3]
    if not selected_ind_ids:
        selected_ind_ids = [i['id'] for i in tracked[:3]]
    active_inds = [i for i in tracked if i['id'] in selected_ind_ids]

    _empty_fig = go.Figure()
    _empty_fig.update_layout(
        height=420,
        paper_bgcolor='#ffffff',
        plot_bgcolor='#ffffff',
        font=dict(color=TEXT, family=FONT),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )

    if not active_inds or mch_full.empty:
        toggle_class = 'mnid-trend-toggle is-bar' if chart_type == 'bar' else 'mnid-trend-toggle is-line'
        toggle_text = 'Bar' if chart_type == 'bar' else 'Line'
        entity_options = facility_options if mode == 'facility' else district_options
        ind_value_out = no_update if user_changed_indicators else selected_ind_ids
        return _empty_fig, entity_options, (selected_entities or []), ind_options, ind_value_out, chart_type, toggle_class, toggle_text

    if mode == 'facility':
        entity_options = facility_options
        default_entities = ([current_fac] if current_fac else []) or [opt['value'] for opt in facility_options[:4]]
        entities = [str(v) for v in (selected_entities or default_entities) if str(v) in {str(opt['value']) for opt in facility_options}]
        entity_labels = {str(opt['value']): str(opt['label']) for opt in facility_options}
        def get_df(entity):
            return mch_full[mch_full['Facility_CODE'] == entity] if 'Facility_CODE' in mch_full.columns else pd.DataFrame()
    else:
        entity_options = district_options
        default_entities = ([current_dist] if current_dist else []) or [opt['value'] for opt in district_options[:4]]
        entities = [str(v) for v in (selected_entities or default_entities) if str(v) in {str(opt['value']) for opt in district_options}]
        entity_labels = {str(opt['value']): str(opt['label']) for opt in district_options}
        def get_df(entity):
            return mch_full[mch_full['District'] == entity] if 'District' in mch_full.columns else pd.DataFrame()

    if not entities:
        toggle_class = 'mnid-trend-toggle is-bar' if chart_type == 'bar' else 'mnid-trend-toggle is-line'
        toggle_text = 'Bar' if chart_type == 'bar' else 'Line'
        ind_value_out = no_update if user_changed_indicators else selected_ind_ids
        return _empty_fig, entity_options, [], ind_options, ind_value_out, chart_type, toggle_class, toggle_text

    if 'Date' not in mch_full.columns:
        toggle_class = 'mnid-trend-toggle is-bar' if chart_type == 'bar' else 'mnid-trend-toggle is-line'
        toggle_text = 'Bar' if chart_type == 'bar' else 'Line'
        ind_value_out = no_update if user_changed_indicators else selected_ind_ids
        return _empty_fig, entity_options, entities, ind_options, ind_value_out, chart_type, toggle_class, toggle_text

    if time_grain == 'daily':
        period_code = 'D'
        period_fmt = lambda p: pd.Period(p, 'D').strftime('%d %b %Y')
        max_periods = 30
    elif time_grain == 'weekly':
        period_code = 'W'
        period_fmt = lambda p: pd.Period(p, 'W').start_time.strftime('%d %b %Y')
        max_periods = 26
    elif time_grain == 'quarterly':
        period_code = 'Q'
        period_fmt = lambda p: f"{p.year} Q{p.quarter}"
        max_periods = 8
    elif time_grain == 'yearly':
        period_code = 'Y'
        period_fmt = lambda p: str(p.year)
        max_periods = 5
    else:
        period_code = 'M'
        period_fmt = lambda p: pd.Period(p, 'M').strftime('%b %Y')
        max_periods = 12

    d2 = mch_full
    d2['_period'] = pd.to_datetime(d2['Date']).dt.to_period(period_code)
    periods = sorted(d2['_period'].dropna().unique())[-max_periods:]

    fig = go.Figure()
    series_idx = 0
    for entity in entities:
        entity_df = get_df(entity)
        if entity_df.empty:
            continue
        for ind in active_inds:
            xs, ys, texts = [], [], []
            for period in periods:
                period_df = entity_df[pd.to_datetime(entity_df['Date']).dt.to_period(period_code) == period]
                _, den, pct = _cov(period_df, ind['numerator_filters'], ind['denominator_filters'])
                xs.append(period_fmt(period))
                ys.append(_display_pct(pct) if den > 0 else None)
                texts.append(f'{pct:.0f}%' if den > 0 else 'No data')
            moving_average, _ = _moving_average_values(ys, time_grain)
            if not any(y is not None for y in moving_average):
                continue
            color = _COMPARE_COLORS[series_idx % len(_COMPARE_COLORS)]
            series_idx += 1
            series_name = f'{entity_labels.get(entity, entity)} | {ind["label"]}'
            if chart_type == 'line':
                fig.add_trace(go.Scatter(
                    name=series_name,
                    x=xs,
                    y=moving_average,
                    mode='lines+markers',
                    line=dict(color=color, width=2.8, shape='linear'),
                    marker=dict(size=6, color=color, line=dict(color='#fff', width=1.4)),
                    customdata=[[raw] for raw in ys],
                    hovertemplate=f'<b>{series_name}</b><br>%{{x}}<br>Moving Avg: %{{y:.1f}}%<br>Raw: %{{customdata[0]:.1f}}%<extra></extra>',
                    connectgaps=False,
                ))
                _tgt = ind.get('target')
                if _tgt is not None:
                    fig.add_trace(go.Scatter(
                        name=f'{entity_labels.get(entity, entity)} | {_target_label(ind)}',
                        x=xs, y=[_tgt] * len(xs),
                        mode='lines',
                        line=dict(color=color, width=1.5, dash='dot'),
                        opacity=0.7, showlegend=False,
                        hovertemplate=f'Target: {_tgt:.0f}%<extra></extra>',
                    ))
            else:
                fig.add_trace(go.Bar(
                    name=series_name,
                    x=xs,
                    y=moving_average,
                    text=texts,
                    textposition='outside',
                    textfont=dict(size=9, color='#E2E8F0'),
                    marker=dict(color=color, opacity=0.88,
                                line=dict(color='rgba(255,255,255,0.25)', width=0.8)),
                    customdata=[[raw] for raw in ys],
                    hovertemplate=f'<b>{series_name}</b><br>%{{x}}<br>Moving Avg: %{{y:.1f}}%<br>Raw: %{{customdata[0]:.1f}}%<extra></extra>',
                ))

    fig.update_layout(
        height=360,
        barmode='group' if chart_type == 'bar' else None,
        bargap=0.20,
        bargroupgap=0.06,
        margin=dict(l=8, r=8, t=12, b=24),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showline=False,
            tickfont=dict(size=10, color=MUTED),
            title=dict(text='Date', font=dict(size=10, color=MUTED)),
        ),
        yaxis=dict(
            title=dict(text='Coverage %', font=dict(size=10, color=MUTED)),
            range=[0, 115],
            showgrid=True,
            gridcolor=GRID_C,
            zeroline=False,
            showline=False,
            tickfont=dict(size=10, color=MUTED),
        ),
        legend=dict(
            orientation='h',
            x=0,
            y=1.05,
            xanchor='left',
            yanchor='bottom',
            font=dict(size=10, color=DIM),
            bgcolor='rgba(0,0,0,0)',
        ),
        hovermode='closest' if chart_type == 'bar' else 'x unified',
    )
    toggle_class = 'mnid-trend-toggle is-bar' if chart_type == 'bar' else 'mnid-trend-toggle is-line'
    toggle_text = 'Bar' if chart_type == 'bar' else 'Line'
    ind_value_out = no_update if user_changed_indicators else selected_ind_ids
    return fig, entity_options, entities, ind_options, ind_value_out, chart_type, toggle_class, toggle_text



def register_mnid_callbacks(app) -> None:
    if getattr(app, '_mnid_callbacks_registered', False):
        return

    app.clientside_callback(
        _MNID_SCROLLSPY_CLIENTSIDE,
        Output('mnid-scrollspy-out', 'data'),
        Input('mnid-scrollspy-tick', 'n_intervals'),
    )

    app.callback(
        Output('mnid-run-charts-container', 'children'),
        Output('mnid-trend-active-cat', 'data'),
        Output({'type': 'trend-cat-btn', 'index': ALL}, 'className'),
        Output('mnid-trend-location', 'options'),
        Output('mnid-trend-ind-filter', 'options'),
        Output('mnid-trend-ind-filter', 'value'),
        Input({'type': 'trend-cat-btn', 'index': ALL}, 'n_clicks'),
        Input('mnid-trend-location', 'value'),
        Input('mnid-trend-ind-filter', 'value'),
        State('mnid-trend-store', 'data'),
        State('mnid-trend-active-cat', 'data'),
        State('mnid-trend-cats-store', 'data'),
        prevent_initial_call=False,
    )(update_trend_chart)

    app.callback(
        Output('mnid-service-table-content', 'children'),
        Output('mnid-service-table-active-cat', 'data'),
        Output({'type': 'service-table-btn', 'index': ALL}, 'className'),
        Output('mnid-service-table-view-store', 'data'),
        Output('mnid-service-table-toggle', 'className'),
        Output('mnid-service-table-toggle-text', 'children'),
        Input('mnid-service-table-toggle', 'n_clicks'),
        Input({'type': 'service-table-btn', 'index': ALL}, 'n_clicks'),
        State('mnid-service-table-store', 'data'),
        State('mnid-service-table-active-cat', 'data'),
        State('mnid-service-table-cats-store', 'data'),
        State('mnid-service-table-view-store', 'data'),
        prevent_initial_call=False,
    )(update_service_table)

    app.callback(
        Output({'type': 'mnid-nav-btn', 'index': ALL}, 'className'),
        Input('mnid-scrollspy-out', 'data'),
        State({'type': 'mnid-nav-btn', 'index': ALL}, 'id'),
        prevent_initial_call=False,
    )(sync_mnid_nav_active_state)

    app.callback(
        Output('mnid-heatmap-graph', 'figure'),
        Output('mnid-heatmap-right', 'children'),
        Output('mnid-heatmap-district-wrap', 'style'),
        Input('mnid-heatmap-view', 'value'),
        Input('mnid-heatmap-district', 'value'),
        Input('mnid-heatmap-indicators', 'value'),
        State('mnid-heatmap-store', 'data'),
        prevent_initial_call=True,
    )(update_heatmap_view)

    app.callback(
        Output('mnid-heatmap-district', 'value'),
        Input('mnid-malawi-treemap', 'clickData'),
        State('mnid-heatmap-store', 'data'),
        prevent_initial_call=True,
    )(sync_district_focus_from_treemap)

    app.callback(
        Output('mnid-performance-heatmap-table', 'children'),
        Output('mnid-performance-aggregate', 'children'),
        Output('mnid-performance-attention', 'children'),
        Input('mnid-performance-indicators', 'value'),
        State('mnid-heatmap-store', 'data'),
        prevent_initial_call=True,
    )(update_performance_heatmap)

    app.callback(
        Output('mnid-compare-bar-chart', 'figure'),
        Output('mnid-compare-entities', 'options'),
        Output('mnid-compare-entities', 'value'),
        Output('mnid-compare-indicators', 'options'),
        Output('mnid-compare-indicators', 'value'),
        Output('mnid-compare-chart-type-store', 'data'),
        Output('mnid-compare-chart-toggle', 'className'),
        Output('mnid-compare-chart-toggle-text', 'children'),
        Input('mnid-compare-mode', 'value'),
        Input('mnid-compare-entities', 'value'),
        Input('mnid-compare-time-grain', 'value'),
        Input('mnid-compare-indicators', 'value'),
        Input('mnid-compare-chart-toggle', 'n_clicks'),
        State('mnid-compare-store', 'data'),
        State('mnid-compare-chart-type-store', 'data'),
    )(update_compare_charts)

    app._mnid_callbacks_registered = True


# MNID dashboard entry point

_network_df_cache: dict = {}


def render_mnid_dashboard(data_opd, config,
                          facility_code, start_date, end_date,
                          scope_meta: dict | None = None):
    dataset_version = (scope_meta or {}).get('dataset_version')
    selected_programs = tuple(sorted((scope_meta or {}).get('mnid_categories') or []))
    selected_facilities = tuple(sorted((scope_meta or {}).get('selected_facilities') or []))
    selected_districts = tuple(sorted((scope_meta or {}).get('selected_districts') or []))
    _opd_key = (
        dataset_version,
        len(data_opd),
        tuple(data_opd.columns.tolist()) if not data_opd.empty else (),
        selected_programs,
        selected_facilities,
        selected_districts,
    )
    if _opd_key not in _network_df_cache:
        _network_df_cache.clear()
        _network_df_cache[_opd_key] = _prepare_mnid_dataframe(data_opd)
    network_df = _network_df_cache[_opd_key]
    primary_bundle = _build_mnid_indicator_content(
        network_df=network_df,
        config=config,
        facility_code=facility_code,
        start_date=start_date,
        end_date=end_date,
        scope_meta=scope_meta,
    )
    facility_df = primary_bundle['facility_df']
    dashboard_theme = primary_bundle['dashboard_theme']

    maternal_content = primary_bundle['indicator_content']
    newborn_content = None
    country_label = 'Maternal'

    if config.get('report_name') == 'Maternal Health':
        newborn_config = _load_mnid_report_config('Newborn')
        if newborn_config:
            newborn_scope_meta = dict(scope_meta or {})
            newborn_scope_meta['mnid_categories'] = newborn_config.get('mnid_categories') or ['Newborn']
            newborn_bundle = _build_mnid_indicator_content(
                network_df=network_df,
                config=newborn_config,
                facility_code=facility_code,
                start_date=start_date,
                end_date=end_date,
                scope_meta=newborn_scope_meta,
            )
            newborn_content = newborn_bundle['indicator_content']
            country_label = 'Maternal & Newborn'

    executive_content = {
        'country-profile': render_country_profile(facility_df, scope_meta=scope_meta, indicator_label=country_label),
        'operational-readiness': render_operational_readiness(
            facility_df,
            supply_inds=primary_bundle['supply_inds'],
            wf_inds=primary_bundle['wf_inds'],
            dq_inds=primary_bundle['dq_inds'],
        ),
        'maternal-dashboard': maternal_content,
    }
    if newborn_content is not None:
        executive_content['newborn-dashboard'] = newborn_content

    executive_token = f'{hash((_opd_key, start_date, end_date, config.get("report_name"), tuple(sorted(executive_content.keys()))))}'
    _MNID_EXECUTIVE_CONTENT_CACHE.clear()
    _MNID_EXECUTIVE_CONTENT_CACHE[executive_token] = executive_content

    tab_children = [
        dcc.Tab(
            label='Country Profile',
            value='country-profile',
            style={'padding': '10px 18px', 'borderRadius': '12px', 'border': f'1px solid {BORDER}', 'backgroundColor': '#FFFFFF', 'color': TEXT},
            selected_style={'padding': '10px 18px', 'borderRadius': '12px', 'border': f'1px solid {BORDER}', 'backgroundColor': '#F0FDF4', 'color': '#15803D', 'fontWeight': 700},
        ),
        dcc.Tab(
            label='Operational Readiness',
            value='operational-readiness',
            style={'padding': '10px 18px', 'borderRadius': '12px', 'border': f'1px solid {BORDER}', 'backgroundColor': '#FFFFFF', 'color': TEXT},
            selected_style={'padding': '10px 18px', 'borderRadius': '12px', 'border': f'1px solid {BORDER}', 'backgroundColor': '#F8FAFC', 'color': '#15803D', 'fontWeight': 700},
        ),
        dcc.Tab(
            label='Maternal',
            value='maternal-dashboard',
            style={'padding': '10px 18px', 'borderRadius': '12px', 'border': f'1px solid {BORDER}', 'backgroundColor': '#FFFFFF', 'color': TEXT},
            selected_style={'padding': '10px 18px', 'borderRadius': '12px', 'border': f'1px solid {BORDER}', 'backgroundColor': '#F8FAFC', 'color': '#15803D', 'fontWeight': 700},
        ),
    ]
    if newborn_content is not None:
        tab_children.append(
            dcc.Tab(
                label='Newborn',
                value='newborn-dashboard',
                style={'padding': '10px 18px', 'borderRadius': '12px', 'border': f'1px solid {BORDER}', 'backgroundColor': '#FFFFFF', 'color': TEXT},
                selected_style={'padding': '10px 18px', 'borderRadius': '12px', 'border': f'1px solid {BORDER}', 'backgroundColor': '#F8FAFC', 'color': '#15803D', 'fontWeight': 700},
            )
        )

    executive_tabs = dcc.Tabs(
        id='mnid-executive-tabs',
        value='country-profile',
        style={'marginBottom': '18px'},
        children=tab_children,
    )

    return html.Div(className=f'mnid-bg{" mnid-theme-newborn" if dashboard_theme == "newborn" else ""}', children=[
        dcc.Interval(id='mnid-scrollspy-tick', interval=250, max_intervals=-1),
        dcc.Store(id='mnid-scrollspy-out'),
        dcc.Store(id='mnid-executive-view-store', data=executive_token),
        html.Div(className=f'mnid-shell{" mnid-shell-newborn" if dashboard_theme == "newborn" else ""}', children=[
            executive_tabs,
            html.Div(id='mnid-executive-content', children=[executive_content['country-profile']]),
        ]),
    ])


@callback(
    Output('mnid-executive-content', 'children'),
    Input('mnid-executive-tabs', 'value'),
    State('mnid-executive-view-store', 'data'),
    prevent_initial_call=False,
)
def _render_mnid_executive_tab(active_tab, executive_token):
    views = _MNID_EXECUTIVE_CONTENT_CACHE.get(executive_token) or {}
    selected = active_tab or 'country-profile'
    return views.get(selected, views.get('country-profile', html.Div()))
