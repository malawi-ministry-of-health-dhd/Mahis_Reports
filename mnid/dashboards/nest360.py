import dash_mantine_components as dmc
from dash import html, dcc

from mnid.aggregation.store import get_aggregate
from mnid.charts.coverage import _coverage_charts_section
from mnid.dashboards.nest360_indicators import get_nest360_indicators
from mnid.views.trends import _trend_switcher


def render_nest360_dashboard(data_opd, facility_code, start_date, end_date, scope_meta=None):
    indicators = get_nest360_indicators()
    agg_df = get_aggregate()

    # Group indicators by subcategory for the renderer
    by_cat = {}
    for ind in indicators:
        cat = ind['subcategory']
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(ind)

    # Categories order
    cat_order = list(by_cat.keys())

    # Use standard renderer for consistency
    # Note: render_mnid_dashboard expects a config object. 
    # Since we are self-contained, we can either pass a dummy or build the layout here.
    # Given the guide, we should return an html.Div.

    layout = html.Div([
        dmc.Title("Nest 360 Newborn & Neonatal Dashboard", order=2, mb="md"),
        dcc.Tabs([
            dcc.Tab([
                html.Div([
                    dmc.Paper([
                        dmc.Text(f"{cat} Overview", fw=700, size="lg", mb="sm"),
                        _coverage_charts_section(
                            {cat: by_cat[cat]},
                            data_opd,
                            categories=[cat],
                            agg_df=agg_df,
                            start_date=start_date,
                            end_date=end_date,
                            facility_codes=[facility_code] if facility_code else None
                        )
                    ], withBorder=True, shadow="sm", p="md", mb="md"),

                    dmc.Paper([
                        dmc.Text(f"{cat} Trends", fw=700, size="lg", mb="sm"),
                        _trend_switcher(
                            agg_df,
                            by_cat[cat],
                            categories=[cat],
                            scope_meta=scope_meta
                        )
                    ], withBorder=True, shadow="sm", p="md")
                ], style={"padding": "16px"})
            ], label=cat, value=cat) for cat in cat_order
        ], value=cat_order[0] if cat_order else None)
    ])

    return layout
