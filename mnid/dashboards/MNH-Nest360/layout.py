"""
MNH-Nest360 dashboard layout.

This module renders the Nest360 Newborn & Neonatal dashboard, which is one of
the tabs inside the MNH Program view (alongside MNH-Beginnings and MNH-MoH).

The dashboard has two main sections:
  1. Coverage — a tabbed view of bar charts, one tab per clinical subcategory
     (Vital signs, CPAP, KMC, Hypothermia, Jaundice, Infection, etc.)
  2. Run charts — trend charts for the same indicators, driven by the selected
     coverage tab and three filter controls (indicator, location, time grain).

Data comes from the MAHIS parquet via the pre-built aggregate (fast path) or
the raw facility_df (fallback). All data is already scope- and date-filtered
by the time it reaches this module — the caller (renderer.py) handles that.
"""

import pandas as pd
import dash_mantine_components as dmc
from dash import html, dcc, callback, Input, Output, State
from dash.exceptions import PreventUpdate

from mnid.aggregation.store import get_aggregate
from mnid.charts.coverage import _coverage_charts_section
from mnid.core.cache import _resolve_scope_filters
from mnid.core.constants import FACILITY_NAMES as _FACILITY_NAMES
from mnid.views.trends import _run_chart_cards
from mnid.core.data_utils import _remember_ui_payload, _restore_ui_dataframe
from .indicators import get_nest360_indicators

# How many indicators to show by default when a coverage tab is first selected.
_DEFAULT_IND_LIMIT = 4


# Callback: update run charts when the user changes anything
#
# Fires when the user:
#   - Clicks a different coverage tab   → shows that subcategory's trends
#   - Changes the indicator filter      → narrows / widens which charts appear
#   - Changes the location dropdown     → filters to a specific district or facility
#   - Changes the time grain            → switches between weekly / monthly / etc.
#
# We use separate component IDs (n360-*) so these controls never clash with the
# main MNID maternal trend section that lives in the MNH-Beginnings tab.
@callback(
    Output('n360-run-charts-container', 'children'),
    Input('n360-subcategory-tabs', 'value'),
    Input('n360-trend-ind-filter', 'value'),
    Input('n360-trend-location', 'value'),
    Input('n360-trend-grain', 'value'),
    State('n360-trend-store', 'data'),
)
def _nest360_sync_trends(tab_value, selected_inds, location, grain, stored):
    if not tab_value or not stored:
        raise PreventUpdate

    # Recover the raw DataFrame from the server-side payload cache.
    # The cache key was stored at render time so we never have to pass large
    # DataFrames over the wire through dcc.Store.
    tracked = stored.get('all_trend_indicators', [])
    df      = _restore_ui_dataframe(stored.get('data_key'))
    agg     = get_aggregate()
    grain   = (grain or 'monthly').strip().lower()

    # Keep only the indicators that belong to the currently selected tab.
    cat_inds = [i for i in tracked if i.get('category') == tab_value]
    if not cat_inds:
        return html.Div(f'No trend data for {tab_value}.',
                        style={'color': '#94A3B8', 'padding': '16px'})

    return _run_chart_cards(
        df, cat_inds, tab_value,
        location=location or 'all',
        selected_ids=selected_inds or None,
        scope_meta=stored.get('scope_meta') or {},
        agg_df=agg,
        fallback_df=df,
        grain=grain,
    )


# Callback: reset indicator filter when the user switches coverage tabs
#
# When the user clicks "CPAP" after having "Vital signs" selected, the indicator
# dropdown should automatically switch to show CPAP indicators (not Vital signs).
@callback(
    Output('n360-trend-ind-filter', 'options'),
    Output('n360-trend-ind-filter', 'value'),
    Input('n360-subcategory-tabs', 'value'),
    State('n360-trend-store', 'data'),
)
def _nest360_update_ind_filter(tab_value, stored):
    if not tab_value or not stored:
        raise PreventUpdate
    tracked  = stored.get('all_trend_indicators', [])
    cat_inds = [i for i in tracked if i.get('category') == tab_value]
    options  = [{'label': i['label'], 'value': i['id']} for i in cat_inds]
    # Select the first N indicators by default so the chart doesn't start blank.
    values   = [o['value'] for o in options[:_DEFAULT_IND_LIMIT]]
    return options, values


def _render_coverage_panel(cat, cat_indicators, data_opd, agg_df, start_date, end_date):
    return html.Div([
        dmc.Paper([
            dmc.Text(f"{cat} — Coverage", fw=700, size="lg", mb="sm"),
            _coverage_charts_section(
                {cat: cat_indicators},
                data_opd,
                categories=[cat],
                agg_df=agg_df,
                start_date=start_date,
                end_date=end_date,
            ),
        ], withBorder=True, shadow="sm", p="md"),
    ], style={'padding': '16px'})


# Callback: build the active coverage tab's charts on demand
#
# Coverage charts used to be built for all 11 subcategories up front on every
# render, even though only one tab is visible at a time - this made every first
# visit to the dashboard far slower than it needed to be. Now only the active
# tab's charts are computed, the same lazy pattern the run-charts section below
# already uses.
@callback(
    Output('n360-coverage-container', 'children'),
    Input('n360-subcategory-tabs', 'value'),
    State('n360-coverage-store', 'data'),
)
def _nest360_sync_coverage(tab_value, stored):
    if not tab_value or not stored:
        raise PreventUpdate
    by_cat = stored.get('by_cat', {})
    cat_indicators = by_cat.get(tab_value, [])
    if not cat_indicators:
        return html.Div(f'No indicators configured for {tab_value}.',
                        style={'color': '#94A3B8', 'padding': '16px'})

    data_opd = _restore_ui_dataframe(stored.get('data_key'))
    agg_df   = _restore_ui_dataframe(stored.get('agg_data_key'))
    if agg_df is not None and agg_df.empty:
        agg_df = None

    return _render_coverage_panel(
        tab_value, cat_indicators, data_opd, agg_df,
        stored.get('start_date'), stored.get('end_date'),
    )


# Main render function
#
# Called by renderer.py when the user clicks the "MNH-Nest360" tab.
# All heavy data loading (scope filtering, date filtering) has already been done
# by the caller — we receive clean, ready-to-use DataFrames here.
def render_mnh_nest360_dashboard(
    facility_df=None,       # date + scope filtered raw rows (has Date column)
    network_df=None,        # full national network df — used for scope resolution
    maternal_config=None,   # not used; kept for interface parity with MNH-MoH
    newborn_config=None,    # not used; kept for interface parity
    start_date=None,
    end_date=None,
    scope_meta=None,        # dict with selected_facilities, selected_districts, etc.
):
    # Only include indicators where data is available in MAHIS.
    # Indicators marked 'awaiting_baseline' are skipped here.
    indicators = [i for i in get_nest360_indicators() if i.get('status') == 'tracked']
    data_opd   = facility_df if facility_df is not None else pd.DataFrame()

    # Narrow the aggregate to the current scope (district / facility selection)
    # so coverage charts and trend charts reflect the active filter.
    agg_df = get_aggregate()
    if agg_df is not None and network_df is not None and scope_meta:
        _, fac_codes, districts = _resolve_scope_filters(network_df, scope_meta)
        if fac_codes:
            agg_df = agg_df[agg_df['facility_code'].isin([str(f) for f in fac_codes])]
        elif districts:
            agg_df = agg_df[agg_df['district'].isin([str(d) for d in districts])]

    # Group indicators by their clinical subcategory to populate the tab layout.
    by_cat: dict = {}
    for ind in indicators:
        by_cat.setdefault(ind['subcategory'], []).append(ind)
    cat_order   = list(by_cat.keys())
    default_cat = cat_order[0] if cat_order else None

    # _run_chart_cards groups by the 'category' field. Since all Nest360
    # indicators share category='Nest360', we remap category → subcategory
    # so the callback can filter correctly per coverage tab.
    trend_indicators = [{**ind, 'category': ind['subcategory']} for ind in indicators]

    # Build location options from the scoped data (district or facility level).
    loc_opts = [{'label': 'All locations', 'value': 'all'}]
    if data_opd is not None and not data_opd.empty:
        if 'District' in data_opd.columns and data_opd['District'].dropna().nunique() > 1:
            for d in sorted(data_opd['District'].dropna().astype(str).unique()):
                loc_opts.append({'label': d, 'value': d})
        elif 'Facility_CODE' in data_opd.columns:
            for fc in sorted(data_opd['Facility_CODE'].dropna().astype(str).unique()):
                loc_opts.append({'label': _FACILITY_NAMES.get(fc, fc), 'value': fc})

    # Indicator filter options and defaults for the initial coverage tab.
    default_cat_inds = [i for i in trend_indicators if i.get('category') == default_cat]
    ind_opts   = [{'label': i['label'], 'value': i['id']} for i in default_cat_inds]
    ind_values = [o['value'] for o in ind_opts[:_DEFAULT_IND_LIMIT]]

    # Store the full indicator list + data key in a dcc.Store so the callbacks
    # can access them without hitting the database again.
    _data_key = _remember_ui_payload('n360_trend', data_opd)
    trend_store = {
        'all_trend_indicators': trend_indicators,
        'data_key': _data_key,
        'scope_meta': scope_meta or {},
    }
    coverage_store = {
        'by_cat': by_cat,
        'data_key': _data_key,
        'agg_data_key': _remember_ui_payload('n360_agg', agg_df if agg_df is not None else pd.DataFrame()),
        'start_date': start_date,
        'end_date': end_date,
    }

    # Pre-render the default tab's run charts so the user sees content immediately
    # instead of a blank page while waiting for the first callback to fire.
    initial_cards = _run_chart_cards(
        data_opd, default_cat_inds, default_cat or '',
        location='all', selected_ids=ind_values,
        scope_meta=scope_meta or {}, agg_df=agg_df, fallback_df=data_opd, grain='monthly',
    ) if default_cat else []

    _dd = {'fontSize': '12px'}

    return html.Div([

        # Section 1: Coverage
        # One tab per clinical subcategory. Only the active tab's charts are ever
        # built - clicking a tab fires _nest360_sync_coverage above instead of all
        # 11 subcategories being computed and shipped to the browser up front.
        dcc.Tabs(
            id='n360-subcategory-tabs',
            value=default_cat,
            children=[
                dcc.Tab(label=cat, value=cat)
                for cat in cat_order
            ],
        ),
        dcc.Store(id='n360-coverage-store', data=coverage_store),
        dcc.Loading(
            html.Div(
                id='n360-coverage-container',
                children=(
                    _render_coverage_panel(default_cat, by_cat[default_cat], data_opd, agg_df, start_date, end_date)
                    if default_cat else []
                ),
            ),
            type='circle', color='#15803d',
        ),

        #  Section 2: Run charts 
        # Shows monthly (or weekly / quarterly / yearly) coverage trends for the
        # indicators in the currently selected coverage tab.
        # The three filter controls mirror what the maternal dashboard provides:
        #   • Indicator filter  — choose which indicators to show as charts
        #   • Location filter   — drill down to a specific district or facility
        #   • Time grain        — switch between weekly, monthly, quarterly, yearly
        html.Div(style={'marginTop': '24px'}, children=[
            html.Div(className='mnid-card', style={'marginBottom': '12px'}, children=[
                dcc.Store(id='n360-trend-store', data=trend_store),

                html.Div(
                    style={'display': 'flex', 'alignItems': 'center',
                           'justifyContent': 'space-between',
                           'marginBottom': '10px', 'gap': '12px', 'flexWrap': 'wrap'},
                    children=[
                        html.Div('RUN CHARTS', className='mnid-section-lbl',
                                 style={'marginBottom': '0'}),
                        html.Div(
                            style={'display': 'flex', 'alignItems': 'center',
                                   'gap': '8px', 'flexWrap': 'wrap'},
                            children=[
                                dcc.Dropdown(
                                    id='n360-trend-ind-filter',
                                    options=ind_opts,
                                    value=ind_values,
                                    multi=True, clearable=True,
                                    placeholder='All indicators',
                                    style={**_dd, 'minWidth': '200px', 'maxWidth': '300px'},
                                ),
                                dcc.Dropdown(
                                    id='n360-trend-location',
                                    options=loc_opts,
                                    value='all',
                                    clearable=False, searchable=True,
                                    placeholder='All locations',
                                    style={**_dd, 'minWidth': '150px', 'maxWidth': '210px'},
                                ),
                                dcc.Dropdown(
                                    id='n360-trend-grain',
                                    options=[
                                        {'label': 'Weekly',    'value': 'weekly'},
                                        {'label': 'Monthly',   'value': 'monthly'},
                                        {'label': 'Quarterly', 'value': 'quarterly'},
                                        {'label': 'Yearly',    'value': 'yearly'},
                                    ],
                                    value='monthly',
                                    clearable=False, searchable=False,
                                    style={**_dd, 'minWidth': '110px'},
                                ),
                            ],
                        ),
                    ],
                ),

                dcc.Loading(
                    html.Div(id='n360-run-charts-container',
                             className='mnid-chart-grid',
                             children=initial_cards),
                    type='circle', color='#15803d',
                ),
            ]),
        ]),
    ])
