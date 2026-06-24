from datetime import datetime

import dash
import dash_mantine_components as dmc
import pandas as pd
from dash import html, dcc, callback, Input, Output

from mnid.dashboards.nest360 import render_nest360_dashboard

dash.register_page(__name__, path='/nest360')

layout = html.Div([
    dcc.Store(id='nest360-store'),
    html.Div(id='nest360-content', children=[
        dmc.Center(dmc.Loader(size="xl"), style={"height": "50vh"})
    ])
])


@callback(
    Output('nest360-content', 'children'),
    [Input('url-params-store', 'data')]
)
def update_nest360(url_params):
    if not url_params:
        return dmc.Alert("No filters provided", color="red")

    location = url_params.get("Location", [None])[0]

    # TODO: load actual data here.
    # For now, we pass an empty DataFrame as the aggregation store is the primary source.
    data_opd = pd.DataFrame()

    # Default date range if not in URL
    start_date = "2026-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")

    try:
        return render_nest360_dashboard(
            data_opd,
            location,
            start_date,
            end_date,
            scope_meta={'location': location}
        )
    except Exception as e:
        import traceback
        return html.Div([
            dmc.Alert(f"Error rendering Nest 360 Dashboard: {str(e)}", color="red"),
            html.Pre(traceback.format_exc())
        ])
