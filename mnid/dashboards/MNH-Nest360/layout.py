"""Nest360 Newborn & Neonatal dashboard layout."""

import dash_mantine_components as dmc
from dash import html, dcc

from mnid.aggregation.store import get_aggregate
from mnid.charts.coverage import _coverage_charts_section
from mnid.views.trends import _trend_switcher
from .indicators import get_nest360_indicators


def render_mnh_nest360_dashboard(
    facility_df=None,
    network_df=None,        # not used — kept for interface parity with MNH-MoH
    maternal_config=None,   # not used — kept for interface parity
    newborn_config=None,    # not used — kept for interface parity
    start_date=None,
    end_date=None,
    scope_meta=None,
):
    import pandas as pd
    indicators = get_nest360_indicators()
    agg_df     = get_aggregate()
    data_opd   = facility_df if facility_df is not None else pd.DataFrame()

    by_cat = {}
    for ind in indicators:
        cat = ind['subcategory']
        by_cat.setdefault(cat, []).append(ind)

    cat_order = list(by_cat.keys())

    return html.Div([
        dcc.Tabs(
            id='nest360-subcategory-tabs',
            value=cat_order[0] if cat_order else None,
            children=[
                dcc.Tab(
                    label=cat,
                    value=cat,
                    children=html.Div([
                        dmc.Paper([
                            dmc.Text(f"{cat} — Coverage", fw=700, size="lg", mb="sm"),
                            _coverage_charts_section(
                                {cat: by_cat[cat]},
                                data_opd,
                                categories=[cat],
                                agg_df=agg_df,
                                start_date=start_date,
                                end_date=end_date,
                            ),
                        ], withBorder=True, shadow="sm", p="md", mb="md"),

                        dmc.Paper([
                            dmc.Text(f"{cat} — Trends", fw=700, size="lg", mb="sm"),
                            _trend_switcher(
                                agg_df if agg_df is not None else data_opd,
                                by_cat[cat],
                                categories=[cat],
                                scope_meta=scope_meta,
                            ),
                        ], withBorder=True, shadow="sm", p="md"),
                    ], style={'padding': '16px'}),
                )
                for cat in cat_order
            ],
        )
    ])
