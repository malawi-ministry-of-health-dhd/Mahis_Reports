"""Heatmap, performance, and compare-chart Dash callbacks, plus register_mnid_callbacks."""
import logging

import pandas as pd
import plotly.graph_objects as go
from dash import html, callback, callback_context, no_update, Input, Output, State
from dash.exceptions import PreventUpdate

from mnid.aggregation.store import (
    get_aggregate as _get_aggregate,
    query_time_series as _agg_time_series,
)
from mnid.charts.chart_helpers import (
    _CAT_LABELS, _cov, _moving_average_values, _display_pct, _target_label,
)
from mnid.core.constants import MUTED, BG, BORDER, TEXT, FONT, GRID_C, DIM
from mnid.charts.heatmap import (
    _build_heatmap_fig, _build_facility_performance_heatmap_fig,
    _build_performance_attention_table,
)
from mnid.charts.layout import _build_district_gauge_row
from mnid.core.cache import _resolve_scope_filters
from mnid.core.constants import (
    FACILITY_NAMES as _FACILITY_NAMES,
    FACILITY_DISTRICT as _FACILITY_DISTRICT,
)
from mnid.core.data_utils import _restore_ui_dataframe

_LOGGER = logging.getLogger(__name__)

_COMPARE_COLORS = [
    '#2563EB', '#0F766E', '#C2410C', '#7C3AED',
    '#DB2777', '#0891B2', '#4D7C0F', '#B45309',
    '#1D4ED8', '#BE185D',
]


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
    fig = _build_heatmap_fig(stored, v, 'All years', district, sel_inds)
    district_style = {'display': 'block'} if v in ('by_district', 'district_facs') else {'display': 'none'}
    return fig, html.Div(), district_style


@callback(
    Output('mnid-heatmap-district', 'value'),
    Input('mnid-malawi-treemap', 'clickData'),
    State('mnid-heatmap-store', 'data'),
    prevent_initial_call=True,
)
def sync_district_focus_from_treemap(click_data, stored):
    if not click_data or not click_data.get('points'):
        raise PreventUpdate

    point  = click_data['points'][0]
    label  = str(point.get('label', '')).strip()
    parent = str(point.get('parent', '')).strip()
    districts = set((stored or {}).get('all_districts', []))

    if label in districts:
        return label
    if parent in districts:
        return parent

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
    Input('mnid-performance-district', 'value'),
    Input('mnid-performance-year', 'value'),
    State('mnid-heatmap-store', 'data'),
    prevent_initial_call=True,
)
def update_performance_heatmap(sel_inds, sel_districts, sel_year, stored):
    if not stored:
        return html.Div(), html.Div(), html.Div()
    year     = sel_year or 'All years'
    district = sel_districts or None
    table    = _build_facility_performance_heatmap_fig(stored, year, district, sel_inds)
    gauges   = _build_district_gauge_row(stored, year)
    attention = _build_performance_attention_table(stored, year, district, 'All', sel_inds)
    return table, gauges, attention


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
def update_compare_charts(mode, selected_entities, time_grain, selected_ind_ids,
                          toggle_clicks, stored, chart_type):
    mode       = mode or 'facility'
    time_grain = time_grain or 'weekly'
    chart_type = chart_type or 'line'

    ctx      = callback_context
    ctx_prop = ctx.triggered[0]['prop_id'] if ctx and ctx.triggered else ''
    user_changed_indicators = ctx_prop == 'mnid-compare-indicators.value'
    user_changed_entities   = ctx_prop == 'mnid-compare-entities.value'
    mode_just_changed       = ctx_prop == 'mnid-compare-mode.value'
    if ctx_prop == 'mnid-compare-chart-toggle.n_clicks':
        chart_type = 'line' if chart_type == 'bar' else 'bar'

    store_payload = stored or {}
    tracked = store_payload.get('tracked', [])

    _compare_agg_check  = _get_aggregate()
    mch_full_fallback   = _restore_ui_dataframe(store_payload.get('data_key'))
    mch_full            = pd.DataFrame() if _compare_agg_check is not None else (mch_full_fallback if mch_full_fallback is not None else pd.DataFrame())

    facility_options = store_payload.get('facility_options', [])
    district_options = store_payload.get('district_options', [])
    current_fac      = store_payload.get('current_fac', '')
    current_dist     = store_payload.get('current_dist', '')
    compare_date_min = pd.to_datetime(store_payload.get('date_min'), errors='coerce')
    compare_date_max = pd.to_datetime(store_payload.get('date_max'), errors='coerce')

    ind_options   = [{'label': i['label'], 'value': i['id']} for i in tracked]
    valid_ind_ids = {opt['value'] for opt in ind_options}
    if selected_ind_ids is None:
        selected_ind_ids = [i['id'] for i in tracked[:2]]
    else:
        selected_ind_ids = [iid for iid in selected_ind_ids if iid in valid_ind_ids][:2]
    active_inds = [i for i in tracked if i['id'] in selected_ind_ids]

    if len(selected_ind_ids) >= 2:
        _sel_set = set(selected_ind_ids)
        ind_options = [{**opt, 'disabled': opt['value'] not in _sel_set} for opt in ind_options]

    _empty_fig = go.Figure()
    _empty_fig.update_layout(height=420, paper_bgcolor='#ffffff', plot_bgcolor='#ffffff',
                              font=dict(color=TEXT, family=FONT),
                              xaxis=dict(visible=False), yaxis=dict(visible=False))

    if not active_inds or (_compare_agg_check is None and mch_full.empty):
        toggle_class = 'mnid-trend-toggle is-bar' if chart_type == 'bar' else 'mnid-trend-toggle is-line'
        toggle_text  = 'Bar' if chart_type == 'bar' else 'Line'
        entity_options = facility_options if mode == 'facility' else district_options
        ind_value_out  = no_update if user_changed_indicators else selected_ind_ids
        return _empty_fig, entity_options, (selected_entities or []), ind_options, ind_value_out, chart_type, toggle_class, toggle_text

    if mode == 'facility':
        entity_options = facility_options
        valid_fac_vals = {str(opt['value']) for opt in facility_options}
        default_entities = ([current_fac] if current_fac and current_fac in valid_fac_vals else []) or [opt['value'] for opt in facility_options[:2]]
        if mode_just_changed:
            entities = [str(v) for v in default_entities if str(v) in valid_fac_vals][:2]
        elif user_changed_entities:
            entities = [str(v) for v in (selected_entities or []) if str(v) in valid_fac_vals][:2]
        else:
            _raw = selected_entities if selected_entities is not None else default_entities
            entities = [str(v) for v in _raw if str(v) in valid_fac_vals][:2]
        entity_labels = {str(opt['value']): str(opt['label']) for opt in facility_options}
        def get_df(entity):
            return mch_full[mch_full['Facility_CODE'] == entity] if 'Facility_CODE' in mch_full.columns else pd.DataFrame()
    else:
        entity_options = district_options
        valid_dist_vals = {str(opt['value']) for opt in district_options}
        default_entities = ([current_dist] if current_dist and current_dist in valid_dist_vals else []) or [opt['value'] for opt in district_options[:2]]
        if mode_just_changed:
            entities = [str(v) for v in default_entities if str(v) in valid_dist_vals][:2]
        elif user_changed_entities:
            entities = [str(v) for v in (selected_entities or []) if str(v) in valid_dist_vals][:2]
        else:
            _raw = selected_entities if selected_entities is not None else default_entities
            entities = [str(v) for v in _raw if str(v) in valid_dist_vals][:2]
        entity_labels = {str(opt['value']): str(opt['label']) for opt in district_options}
        def get_df(entity):
            return mch_full[mch_full['District'] == entity] if 'District' in mch_full.columns else pd.DataFrame()

    if len(entities) >= 2:
        _ent_set = set(entities)
        entity_options = [{**opt, 'disabled': opt['value'] not in _ent_set} for opt in entity_options]

    toggle_class  = 'mnid-trend-toggle is-bar' if chart_type == 'bar' else 'mnid-trend-toggle is-line'
    toggle_text   = 'Bar' if chart_type == 'bar' else 'Line'
    ind_value_out = no_update if user_changed_indicators else selected_ind_ids

    if not entities:
        return _empty_fig, entity_options, [], ind_options, ind_value_out, chart_type, toggle_class, toggle_text

    if _compare_agg_check is None and 'Date' not in mch_full.columns:
        return _empty_fig, entity_options, entities, ind_options, ind_value_out, chart_type, toggle_class, toggle_text

    # Grain config
    _grain_cfg = {
        'daily':     ('D', lambda p: pd.Period(p, 'D').strftime('%d %b %Y'), 30),
        'weekly':    ('W', lambda p: pd.Period(p, 'W').start_time.strftime('%d %b %Y'), 26),
        'quarterly': ('Q', lambda p: f"{p.year} Q{p.quarter}", 8),
        'yearly':    ('Y', lambda p: str(p.year), 5),
        'monthly':   ('M', lambda p: pd.Period(p, 'M').strftime('%b %Y'), 12),
    }
    period_code, period_fmt, max_periods = _grain_cfg.get(time_grain, _grain_cfg['monthly'])

    _compare_agg = _get_aggregate()
    if _compare_agg is None:
        d2 = mch_full.copy()
        d2['_period'] = pd.to_datetime(d2['Date']).dt.to_period(period_code)
        periods = sorted(d2['_period'].dropna().unique())[-max_periods:]
    else:
        periods = []

    fig = go.Figure()
    series_idx = 0
    for entity in entities:
        for ind in active_inds:
            xs, ys, texts = [], [], []
            if _compare_agg is not None:
                fac_arg  = [entity] if mode == 'facility' else None
                dist_arg = [entity] if mode == 'district' else None
                series   = _agg_time_series(
                    _compare_agg, ind['id'], grain=time_grain,
                    facility_codes=fac_arg, districts=dist_arg,
                    start_date=None if pd.isna(compare_date_min) else compare_date_min,
                    end_date=None if pd.isna(compare_date_max) else compare_date_max,
                    indicator_label=ind.get('label'),
                )
                series = series.tail(max_periods)
                if not series.empty:
                    xs    = [period_fmt(pd.Period(ts, period_code)) for ts in
                             pd.to_datetime(series['period_start']).dt.to_period(period_code)]
                    ys    = series['pct'].tolist()
                    ys    = [y if (series['denominator'].iloc[i] > 0) else None for i, y in enumerate(ys)]
                    texts = [f'{y:.0f}%' if y is not None else 'No data' for y in ys]

            if not xs and mch_full_fallback is not None and not mch_full_fallback.empty and 'Date' in mch_full_fallback.columns:
                _col = 'Facility_CODE' if mode == 'facility' else 'District'
                if _col in mch_full_fallback.columns:
                    _efb = mch_full_fallback[mch_full_fallback[_col].astype(str) == str(entity)].copy()
                    if not _efb.empty:
                        _efb['_period'] = pd.to_datetime(_efb['Date']).dt.to_period(period_code)
                        for _p in sorted(_efb['_period'].dropna().unique())[-max_periods:]:
                            _pf = _efb[_efb['_period'] == _p]
                            _, _den, _pct = _cov(_pf, ind['numerator_filters'], ind['denominator_filters'])
                            xs.append(period_fmt(_p))
                            ys.append(_display_pct(_pct) if _den > 0 else None)
                            texts.append(f'{_pct:.0f}%' if _den > 0 else 'No data')

            # Last resort: scan raw entity df directly. Runs when the aggregate had no
            # matching rows (e.g. stale aggregate with old indicator IDs) AND the UI
            # cache was cold. mch_full contains the full scoped dataframe.
            if not xs:
                entity_df = get_df(entity)
                if entity_df.empty:
                    continue
                entity_df = entity_df.copy()
                entity_df['_period'] = pd.to_datetime(entity_df['Date'], errors='coerce').dt.to_period(period_code)
                for _p in sorted(entity_df['_period'].dropna().unique())[-max_periods:]:
                    _pf = entity_df[entity_df['_period'] == _p]
                    _, _den, _pct = _cov(_pf, ind['numerator_filters'], ind['denominator_filters'])
                    xs.append(period_fmt(_p))
                    ys.append(_display_pct(_pct) if _den > 0 else None)
                    texts.append(f'{_pct:.0f}%' if _den > 0 else 'No data')

            if not xs:
                continue
            moving_average, _ = _moving_average_values(ys, time_grain)
            if not any(y is not None for y in moving_average):
                continue

            color       = _COMPARE_COLORS[series_idx % len(_COMPARE_COLORS)]
            series_idx += 1
            series_name = f'{entity_labels.get(entity, entity)} | {ind["label"]}'

            if chart_type == 'line':
                valid_ys = [y for y in ys if y is not None]
                avg      = sum(valid_ys) / len(valid_ys) if valid_ys else None
                if avg is not None:
                    fig.add_trace(go.Scatter(
                        x=xs, y=[avg] * len(xs), mode='lines',
                        line=dict(color=color, width=1.2, dash='dash'),
                        showlegend=False, opacity=0.55,
                        hovertemplate=f'Mean {entity_labels.get(entity, entity)}: {avg:.0f}%<extra></extra>',
                    ))
                fig.add_trace(go.Scatter(
                    name=series_name, x=xs, y=moving_average,
                    mode='lines+markers',
                    line=dict(color=color, width=2.8, shape='linear'),
                    marker=dict(size=6, color=color, line=dict(color='#fff', width=1.4)),
                    customdata=[[raw] for raw in ys], connectgaps=False,
                    hovertemplate=f'<b>{series_name}</b><br>%{{x}}<br>Moving Avg: %{{y:.1f}}%<br>Raw: %{{customdata[0]:.1f}}%<extra></extra>',
                ))
                _tgt = ind.get('target')
                if _tgt is not None:
                    fig.add_trace(go.Scatter(
                        name=f'{entity_labels.get(entity, entity)} | {_target_label(ind)}',
                        x=xs, y=[_tgt] * len(xs), mode='lines',
                        line=dict(color=color, width=1.5, dash='dot'),
                        opacity=0.7, showlegend=False,
                        hovertemplate=f'Target: {_tgt:.0f}%<extra></extra>',
                    ))
            else:
                fig.add_trace(go.Bar(
                    name=series_name, x=xs, y=moving_average, text=texts,
                    textposition='outside', textfont=dict(size=9, color='#E2E8F0'),
                    marker=dict(color=color, opacity=0.88, line=dict(color='rgba(255,255,255,0.25)', width=0.8)),
                    customdata=[[raw] for raw in ys],
                    hovertemplate=f'<b>{series_name}</b><br>%{{x}}<br>Moving Avg: %{{y:.1f}}%<br>Raw: %{{customdata[0]:.1f}}%<extra></extra>',
                ))

    fig.update_layout(
        height=360, barmode='group' if chart_type == 'bar' else None,
        bargap=0.20, bargroupgap=0.06, margin=dict(l=8, r=8, t=12, b=24),
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED),
                   title=dict(text='Date', font=dict(size=10, color=MUTED))),
        yaxis=dict(title=dict(text='Coverage %', font=dict(size=10, color=MUTED)),
                   range=[0, 115], showgrid=True, gridcolor=GRID_C,
                   zeroline=False, showline=False, tickfont=dict(size=10, color=MUTED)),
        legend=dict(orientation='h', x=0, y=1.05, xanchor='left', yanchor='bottom',
                    font=dict(size=10, color=DIM), bgcolor='rgba(0,0,0,0)'),
        hovermode='closest' if chart_type == 'bar' else 'x unified',
    )
    return fig, entity_options, entities, ind_options, ind_value_out, chart_type, toggle_class, toggle_text


def register_mnid_callbacks(app) -> None:
    """Register all MNID callbacks with an explicit Dash app instance."""
    if getattr(app, '_mnid_callbacks_registered', False):
        return

    from mnid.views.trends import update_trend_chart
    from mnid.views.service_table import update_service_table
    from mnid.views.renderer import _render_mnid_executive_tab, _update_country_profile_chart_grain, _preload_mnid_executive_tabs
    from dash import ALL, MATCH

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
        Input('mnid-trend-grain', 'value'),
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
        Input('mnid-performance-district', 'value'),
        Input('mnid-performance-year', 'value'),
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

    app.callback(
        Output('mnid-executive-content', 'children'),
        Input('mnid-executive-tabs', 'value'),
        State('mnid-executive-view-store', 'data'),
        prevent_initial_call=False,
    )(_render_mnid_executive_tab)

    app.callback(
        Output({'type': 'mnid-cp-graph',   'chart': MATCH}, 'figure'),
        Output({'type': 'mnid-cp-caption', 'chart': MATCH}, 'children'),
        Input({'type': 'mnid-cp-grain',    'chart': MATCH}, 'value'),
        State({'type': 'mnid-cp-series',   'chart': MATCH}, 'data'),
        State({'type': 'mnid-cp-meta',     'chart': MATCH}, 'data'),
        prevent_initial_call=False,
    )(_update_country_profile_chart_grain)

    app.callback(
        Output('mnid-preload-status', 'data'),
        Input('mnid-background-preload', 'n_intervals'),
        State('mnid-executive-view-store', 'data'),
        State('mnid-executive-tabs', 'value'),
        prevent_initial_call=False,
    )(_preload_mnid_executive_tabs)

    app._mnid_callbacks_registered = True
