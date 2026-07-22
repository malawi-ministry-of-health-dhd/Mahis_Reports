"""Run-chart figures, trend-switcher layout, and trend Dash callbacks."""
import json
import logging

import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc, callback, callback_context, no_update, Input, Output, State, ALL

from mnid.core.cache import _resolve_scope_filters
from mnid.aggregation.store import (
    get_aggregate as _get_aggregate,
    query_coverage as _agg_coverage,
    query_time_series as _agg_time_series,
    _floor_to_period as _agg_floor_period,
    _candidate_grains as _agg_candidate_grains,
    resolve_indicator_id as _agg_resolve_id,
)
from mnid.charts.chart_helpers import (
    _CAT_LABELS, _CAT_ORDER,
    _cov, _css, _moving_average_values,
    CAT_PALETTES, _TREND_SERIES_PALETTE,
)
from mnid.charts.heatmap import _mask
from mnid.core.constants import MUTED, FACILITY_NAMES as _FACILITY_NAMES
from mnid.core.indicators import _resolve_category_order
from mnid.core.data_utils import _remember_ui_payload, _restore_ui_dataframe
from mnid.components.run_charts import _format_grain_label, _hex_to_rgba

_LOGGER = logging.getLogger(__name__)
_DEFAULT_TREND_INDICATOR_LIMIT = 4


_MNID_SCROLLSPY_CLIENTSIDE = """
function(_tick) {
    const sections = [
        '#mnid-summary',
        '#mnid-coverage',
        '#mnid-trends',
        '#mnid-performance',
        '#mnid-heatmap',
        '#mnid-comparative'
    ];

    let active = '#mnid-summary';
    const activationLine = 124;
    let bestPassed = null;
    let nextUpcoming = null;

    for (const selector of sections) {
        const el = document.querySelector(selector);
        if (!el) { continue; }
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


def _trend_period_context(plot_df: pd.DataFrame, grain: str) -> tuple[pd.DataFrame, list, str, str]:
    working = plot_df.copy()
    dates = pd.to_datetime(working['Date'], errors='coerce')
    grain = (grain or 'monthly').strip().lower()
    if grain == 'weekly':
        tickfmt, hfmt = '%d %b', '%d %b %Y'
        working['_p'] = dates.dt.to_period('W').dt.start_time
    elif grain == 'quarterly':
        tickfmt, hfmt = '%b %Y', '%b %Y'
        working['_p'] = dates.dt.to_period('Q').dt.start_time
    elif grain == 'yearly':
        tickfmt, hfmt = '%Y', '%Y'
        working['_p'] = dates.dt.to_period('Y').dt.start_time
    else:
        tickfmt, hfmt = '%b %y', '%b %Y'
        working['_p'] = dates.dt.to_period('M').dt.start_time
        grain = 'monthly'
    periods = sorted(working['_p'].dropna().unique())
    return working, periods, tickfmt, hfmt


def _trend_scope_filters(
    df: pd.DataFrame, location: str | None = None
) -> tuple[pd.DataFrame, list[str] | None, list[str] | None]:
    plot_df = df.copy()
    fac_filter: list[str] | None = None
    dist_filter: list[str] | None = None
    if location and location != 'all':
        if 'Facility_CODE' in df.columns:
            mask = df['Facility_CODE'].astype(str) == str(location)
            if mask.any():
                plot_df = df[mask].copy()
                fac_filter = [str(location)]
        if fac_filter is None and 'District' in df.columns:
            mask = df['District'].astype(str) == str(location)
            if mask.any():
                plot_df = df[mask].copy()
                dist_filter = [str(location)]
    return plot_df, fac_filter, dist_filter


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


def _indicator_run_fig(
    plot_df: pd.DataFrame, ind: dict, color: str,
    periods: list, tickfmt: str, hfmt: str,
    grain: str = 'monthly',
    precomputed: pd.DataFrame | None = None,
) -> go.Figure:
    if precomputed is not None and not precomputed.empty:
        xs     = precomputed['period_start'].tolist()
        ys     = precomputed['pct'].tolist()
        n_vals = precomputed['numerator'].tolist()
        d_vals = precomputed['denominator'].tolist()
        ys = [y if d > 0 else None for y, d in zip(ys, d_vals)]
    elif not (ind.get('numerator_filters') and ind.get('denominator_filters')):
        xs, ys, n_vals, d_vals = list(periods), [None] * len(periods), [0] * len(periods), [0] * len(periods)
    else:
        nm  = _mask(plot_df, ind['numerator_filters'])
        dm  = _mask(plot_df, ind['denominator_filters'])
        pid = 'person_id'
        xs, ys, n_vals, d_vals = [], [], [], []
        for p in periods:
            pm    = plot_df['_p'] == p
            n_val = int(plot_df.loc[pm & nm, pid].dropna().nunique()) if pid in plot_df.columns else int((pm & nm).sum())
            d_val = int(plot_df.loc[pm & dm, pid].dropna().nunique()) if pid in plot_df.columns else int((pm & dm).sum())
            xs.append(p)
            ys.append(round(n_val / d_val * 100, 1) if d_val > 0 else None)
            n_vals.append(n_val)
            d_vals.append(d_val)

    period_labels = [_format_grain_label(pd.Timestamp(x), grain) for x in xs]
    smoothed, _   = _moving_average_values(ys, grain)
    valid_ys      = [y for y in smoothed if y is not None]
    if not valid_ys:
        return go.Figure(layout={
            'paper_bgcolor': 'white', 'plot_bgcolor': 'white', 'height': 220,
            'margin': {'l': 16, 'r': 16, 't': 10, 'b': 28},
            'xaxis': {'visible': False}, 'yaxis': {'visible': False},
            'annotations': [{'text': 'No data for this period',
                              'xref': 'paper', 'yref': 'paper', 'x': 0.5, 'y': 0.5,
                              'showarrow': False,
                              'font': {'size': 13, 'color': '#94a3b8', 'family': 'Geist, system-ui, sans-serif'}}],
        })

    target = ind.get('target')
    traces = []
    if target is not None:
        traces.append(go.Scatter(
            x=period_labels, y=[target] * len(period_labels), mode='lines',
            line={'color': '#94A3B8', 'width': 1.4, 'dash': 'dot'},
            showlegend=False,
            hovertemplate=f'Target: {target}%<extra></extra>',
        ))

    valid_pts = [(x, label, y, raw) for x, label, y, raw in zip(xs, period_labels, smoothed, ys) if y is not None]
    kp_set, key_pts = set(), []
    for pt in [valid_pts[0], valid_pts[-1]]:
        if pt[1] not in kp_set:
            kp_set.add(pt[1])
            key_pts.append(pt)
    traces.append(go.Scatter(
        x=[p[1] for p in key_pts], y=[p[2] for p in key_pts],
        mode='markers+text',
        text=[f'{p[2]:.0f}%' for p in key_pts],
        textposition='top center',
        textfont={'size': 10, 'color': '#475569', 'family': 'Geist, system-ui, sans-serif'},
        marker={'size': 0, 'color': color},
        showlegend=False,
        hovertemplate='%{x}: %{y:.0f}%<extra></extra>',
    ))
    traces.append(go.Scatter(
        x=period_labels, y=smoothed, mode='lines+markers',
        line={'color': color, 'width': 3.2, 'shape': 'spline', 'smoothing': 0.45},
        marker={'size': 6, 'color': color, 'line': {'color': '#fff', 'width': 1.2}},
        fill='tozeroy', fillcolor=_hex_to_rgba(color, 0.08),
        connectgaps=False, showlegend=False,
        customdata=list(zip(period_labels, n_vals, d_vals, ys)),
        hovertemplate=(
            '<b>%{customdata[0]}</b><br>'
            'Moving avg: <b>%{y:.1f}%</b><br>'
            'Actual: <b>%{customdata[3]:.1f}%</b><br>'
            'Clients: %{customdata[1]} / %{customdata[2]}'
            '<extra></extra>'
        ),
    ))

    layout_annotations = []
    if target is not None:
        layout_annotations.append({
            'x': 1.005, 'y': target / 112, 'xref': 'paper', 'yref': 'paper',
            'text': f'target {target:.0f}%', 'showarrow': False,
            'font': {'size': 10, 'color': '#64748B', 'family': 'Geist, system-ui, sans-serif'},
            'xanchor': 'left', 'yanchor': 'middle',
        })
    tick_angle = -28 if grain in {'daily', 'weekly', 'monthly'} else 0
    return go.Figure(data=traces, layout={
        'paper_bgcolor': 'white', 'plot_bgcolor': 'white',
        'font': {'family': 'Geist, system-ui, sans-serif', 'color': '#64748b', 'size': 11},
        'height': 220, 'margin': {'l': 42, 'r': 24, 't': 16, 'b': 44},
        'showlegend': False, 'hovermode': 'x unified',
        'hoverlabel': {
            'bgcolor': '#0f172a', 'bordercolor': '#0f172a',
            'font_size': 11, 'font_family': 'Geist, system-ui, sans-serif', 'font_color': '#ffffff',
        },
        'xaxis': {
            'showgrid': False, 'zeroline': False, 'showline': False,
            'type': 'category', 'tickfont': {'size': 10, 'color': '#94a3b8'},
            'tickangle': tick_angle, 'automargin': True,
        },
        'yaxis': {
            'showgrid': True, 'gridcolor': '#e2e8f0', 'gridwidth': 1,
            'zeroline': False, 'showline': False,
            'tickfont': {'size': 10, 'color': '#94a3b8'}, 'ticksuffix': '%', 'range': [0, 112],
        },
        'annotations': layout_annotations,
    })


def _run_chart_cards(
    df: pd.DataFrame, indicators: list, cat: str,
    location: str | None = None,
    selected_ids: list | None = None,
    scope_meta: dict | None = None,
    agg_df: pd.DataFrame | None = None,
    fallback_df: pd.DataFrame | None = None,
    grain: str = 'monthly',
) -> list:
    tracked = [i for i in indicators if i.get('status') == 'tracked' and i.get('category') == cat]
    if selected_ids:
        id_set = set(selected_ids)
        tracked = [i for i in tracked if i.get('id') in id_set] or tracked
    if not tracked:
        return [html.Div('No indicators configured for this category.',
                         style={'color': MUTED, 'fontSize': '13px', 'padding': '24px'})]

    # DHIS2-backed dashboards intentionally have no encounter-level MAHIS
    # dataframe. Use the aggregate's period bounds to drive the charts instead
    # of treating the empty raw dataframe as an unconfigured category.
    if df is None or df.empty:
        if agg_df is None:
            agg_df = _get_aggregate(route=(scope_meta or {}).get('route', 'default'))
        if agg_df is None or agg_df.empty or 'period_start' not in agg_df.columns:
            return [html.Div('No data is available for this category.',
                             style={'color': MUTED, 'fontSize': '13px', 'padding': '24px'})]
        aggregate_dates = pd.to_datetime(agg_df['period_start'], errors='coerce').dropna()
        if aggregate_dates.empty:
            return [html.Div('No data is available for this category.',
                             style={'color': MUTED, 'fontSize': '13px', 'padding': '24px'})]
        df = pd.DataFrame({'Date': [aggregate_dates.min(), aggregate_dates.max()]})

    source_df = fallback_df if fallback_df is not None and not fallback_df.empty else df
    plot_df, fac_filter, dist_filter = _trend_scope_filters(source_df, location)
    dates = pd.to_datetime(plot_df['Date'], errors='coerce').dropna() if 'Date' in plot_df.columns else pd.Series([], dtype='datetime64[ns]')
    if dates.empty:
        return [html.Div('No data for the selected location.',
                         style={'color': MUTED, 'fontSize': '13px', 'padding': '24px'})]

    plot_df, periods, tickfmt, hfmt = _trend_period_context(plot_df, grain)
    periods = sorted(plot_df['_p'].dropna().unique())
    if not periods:
        return [html.Div('No time periods available.',
                         style={'color': MUTED, 'fontSize': '13px', 'padding': '24px'})]

    date_min, date_max = dates.min(), dates.max()

    if agg_df is None:
        agg_df = _get_aggregate(route=(scope_meta or {}).get('route', 'default'))
    if fac_filter is None and dist_filter is None and scope_meta:
        _, fac_codes, districts = _resolve_scope_filters(plot_df, scope_meta)
        fac_filter  = fac_codes or None
        dist_filter = districts or None

    _agg_slice = None
    if agg_df is not None and not agg_df.empty:
        _ind_ids   = {_agg_resolve_id(agg_df, i['id'], i.get('label')) for i in tracked}
        _grain_set = set(_agg_candidate_grains(grain))
        _pf = min(_agg_floor_period(date_min, g) for g in _grain_set)
        _smask = (
            agg_df['grain'].isin(_grain_set)
            & agg_df['indicator_id'].isin(_ind_ids)
            & (agg_df['period_start'] >= _pf)
            & (agg_df['period_start'] <= pd.Timestamp(date_max))
        )
        if fac_filter:
            _smask &= agg_df['facility_code'].isin([str(f) for f in fac_filter])
        elif dist_filter:
            _smask &= agg_df['district'].isin([str(d) for d in dist_filter])
        _agg_slice = agg_df[_smask].reset_index(drop=True)

    cat_colors = CAT_PALETTES.get(cat, _TREND_SERIES_PALETTE)
    cards = []

    for idx, ind in enumerate(tracked):
        color = cat_colors[idx % len(cat_colors)]

        precomputed = None
        if _agg_slice is not None:
            precomputed = _agg_time_series(
                _agg_slice, ind['id'], grain=grain,
                facility_codes=fac_filter,
                districts=dist_filter if not fac_filter else None,
                start_date=date_min, end_date=date_max,
                indicator_label=ind.get('label'),
            )

        # When aggregate has no data fall back to raw df
        if (precomputed is None or precomputed.empty) and fallback_df is not None and not fallback_df.empty:
            _fb = fallback_df.copy()
            if location and location != 'all':
                if 'Facility_CODE' in _fb.columns:
                    _lm = _fb['Facility_CODE'].astype(str) == str(location)
                    if _lm.any():
                        _fb = _fb[_lm]
                elif 'District' in _fb.columns:
                    _lm = _fb['District'].astype(str) == str(location)
                    if _lm.any():
                        _fb = _fb[_lm]
            _fb_dates = pd.to_datetime(_fb['Date'], errors='coerce').dropna() if 'Date' in _fb.columns else pd.Series([], dtype='datetime64[ns]')
            if not _fb_dates.empty:
                _fb, _fb_periods, _fb_tickfmt, _fb_hfmt = _trend_period_context(_fb, grain)
                fig = _indicator_run_fig(_fb, ind, color, _fb_periods, _fb_tickfmt, _fb_hfmt, grain, precomputed=None)
            else:
                fig = _indicator_run_fig(plot_df, ind, color, periods, tickfmt, hfmt, grain, precomputed=None)
        else:
            fig = _indicator_run_fig(plot_df, ind, color, periods, tickfmt, hfmt, grain, precomputed=precomputed)

        target       = ind.get('target')
        target_badge = None
        if target is not None:
            if _agg_slice is not None:
                cur_pct = _agg_coverage(_agg_slice, ind['id'], date_min, date_max,
                                        facility_codes=fac_filter,
                                        districts=dist_filter if not fac_filter else None,
                                        grain=grain, indicator_label=ind.get('label'))[2]
            elif ind.get('numerator_filters') and ind.get('denominator_filters'):
                cur_pct = _cov(plot_df, ind['numerator_filters'], ind['denominator_filters'])[2]
            else:
                cur_pct = 0.0
            cls = _css(cur_pct, target, ind)
            badge_colors = {'ok': ('#D1FAE5', '#065F46'), 'warn': ('#FEF3C7', '#92400E'), 'danger': ('#FEE2E2', '#991B1B')}
            bg, fg = badge_colors.get(cls, ('#F1F5F9', '#475569'))
            target_badge = html.Span(
                f'Target {target}%',
                style={'fontSize': '10px', 'fontWeight': '600', 'padding': '2px 7px',
                       'borderRadius': '999px', 'backgroundColor': bg, 'color': fg,
                       'marginLeft': '6px'},
            )

        card = html.Div(className='mnid-chart-card', children=[
            html.Div(
                style={'display': 'flex', 'alignItems': 'center',
                       'justifyContent': 'space-between', 'marginBottom': '2px'},
                children=[
                    html.Div(ind['label'], style={
                        'fontSize': '11px', 'fontWeight': '600', 'color': '#0F172A', 'lineHeight': '1.3',
                    }),
                    target_badge,
                ],
            ),
            dcc.Graph(
                figure=fig,
                config={
                    'displayModeBar': 'hover',
                    'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'],
                    'toImageButtonOptions': {'format': 'png', 'scale': 2},
                    'responsive': True,
                },
                style={'height': '200px'},
            ),
        ])
        cards.append(card)

    return cards


def _trend_switcher(
    df: pd.DataFrame, indicators: list,
    categories: list | None = None,
    default_cat: str | None = None,
    scope_meta: dict | None = None,
    payload_key: str | None = None,
) -> html.Div:
    tracked     = [i for i in indicators if i.get('status') == 'tracked']
    cat_order   = _resolve_category_order(tracked, categories)
    default_cat = default_cat if default_cat in cat_order else (cat_order[0] if cat_order else 'ANC')
    loc_options = _location_options_for_df(df, scope_meta or {})

    ind_opts_by_cat = {
        c: [{'label': i['label'], 'value': i['id']} for i in tracked if i.get('category') == c]
        for c in cat_order
    }
    default_ind_opts   = ind_opts_by_cat.get(default_cat, [])
    default_ind_values = [o['value'] for o in default_ind_opts[:_DEFAULT_TREND_INDICATOR_LIMIT]]

    try:
        _dates    = pd.to_datetime(df['Date'], errors='coerce').dropna() if 'Date' in df.columns else pd.Series([], dtype='datetime64[ns]')
        _date_min = _dates.min().isoformat() if len(_dates) else None
        _date_max = _dates.max().isoformat() if len(_dates) else None
    except Exception:
        _date_min = _date_max = None

    trend_store = {
        'tracked':         tracked,
        'data_key':        _remember_ui_payload('trend', df, stable_key=payload_key),
        'date_min':        _date_min,
        'date_max':        _date_max,
        'scope_meta':      scope_meta or {},
        'loc_options':     loc_options,
        'ind_opts_by_cat': ind_opts_by_cat,
    }

    return html.Div(className='mnid-card', style={'marginBottom': '12px'}, children=[
        html.Div(
            style={'display': 'flex', 'alignItems': 'center',
                   'justifyContent': 'space-between', 'marginBottom': '10px',
                   'gap': '12px', 'flexWrap': 'wrap'},
            children=[
                html.Div('RUN CHARTS', className='mnid-section-lbl', style={'marginBottom': '0'}),
                html.Div(
                    style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'flexWrap': 'wrap'},
                    children=[
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
                            value=default_ind_values,
                            multi=True, clearable=True,
                            placeholder='All indicators',
                            style={'minWidth': '200px', 'maxWidth': '300px', 'fontSize': '12px'},
                        ),
                        dcc.Dropdown(
                            id='mnid-trend-location',
                            options=loc_options,
                            value='all',
                            clearable=False, searchable=True,
                            placeholder='All locations',
                            style={'minWidth': '150px', 'maxWidth': '210px', 'fontSize': '12px'},
                        ),
                        dcc.Dropdown(
                            id='mnid-trend-grain',
                            options=[
                                {'label': 'Weekly',    'value': 'weekly'},
                                {'label': 'Monthly',   'value': 'monthly'},
                                {'label': 'Quarterly', 'value': 'quarterly'},
                                {'label': 'Yearly',    'value': 'yearly'},
                            ],
                            value='monthly',
                            clearable=False,
                            searchable=False,
                            style={'minWidth': '110px', 'fontSize': '12px'},
                        ),
                    ],
                ),
            ],
        ),
        dcc.Store(id='mnid-trend-store', data=trend_store),
        dcc.Store(id='mnid-trend-active-cat', data=default_cat),
        dcc.Store(id='mnid-trend-cats-store', data=cat_order),
        dcc.Loading(
            html.Div(id='mnid-run-charts-container', className='mnid-chart-grid', children=[]),
            type='circle', color='#15803d',
        ),
    ])


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
    Input('mnid-trend-grain', 'value'),
    State('mnid-trend-store', 'data'),
    State('mnid-trend-active-cat', 'data'),
    State('mnid-trend-cats-store', 'data'),
    prevent_initial_call=False,
)
def update_trend_chart(n_clicks_list, location, selected_inds, grain, stored_trend, active_cat, cat_order):
    grain      = (grain or 'monthly').strip().lower()
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

    trend_payload   = stored_trend or {}
    tracked         = trend_payload.get('tracked', [])
    scope_meta      = trend_payload.get('scope_meta') or {}
    loc_options     = trend_payload.get('loc_options') or [{'label': 'All locations', 'value': 'all'}]
    ind_opts_by_cat = trend_payload.get('ind_opts_by_cat') or {}
    ind_options     = ind_opts_by_cat.get(cat, [])

    _agg_now = _get_aggregate(route=scope_meta.get('route', 'default'))
    _df_full = _restore_ui_dataframe(trend_payload.get('data_key'))
    if _agg_now is not None:
        _d_min = trend_payload.get('date_min')
        _d_max = trend_payload.get('date_max')
        df = (
            pd.DataFrame({'Date': pd.to_datetime([_d_min, _d_max])})
            if (_d_min and _d_max) else
            (_df_full if _df_full is not None else pd.DataFrame())
        )
    else:
        df = _df_full if _df_full is not None else pd.DataFrame()

    default_ind_values = [o['value'] for o in ind_options[:_DEFAULT_TREND_INDICATOR_LIMIT]]
    ind_value_out = default_ind_values if cat_changed else no_update

    cards   = _run_chart_cards(
        df, tracked, cat, location or 'all',
        default_ind_values if cat_changed else selected_inds,
        scope_meta, agg_df=_agg_now, fallback_df=_df_full, grain=grain,
    )
    # Truncate to match the number of buttons actually on the page.
    # On initial page load the maternal tab hasn't rendered yet so n_clicks_list=[]
    # — returning an empty list avoids the "Expected 0, got N" callback error.
    all_classes = ['mnid-filter-btn active' if c == cat else 'mnid-filter-btn' for c in categories]
    classes = all_classes[:len(n_clicks_list)]
    return cards, cat, classes, loc_options, ind_options, ind_value_out
