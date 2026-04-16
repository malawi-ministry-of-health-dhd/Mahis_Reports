"""
MNID dashboard renderer.

This module builds the Maternal and Child Health dashboard layout,
calculates configured indicator coverage, and renders the main dashboard
sections such as trends, comparison views, heatmaps, and readiness panels.
"""
from dash import html, dcc, clientside_callback, callback, callback_context, Input, Output, State, ALL
from dash.exceptions import PreventUpdate
import dash_mantine_components as dmc
from helpers.helpers import create_count_from_config
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import json
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
)
from mnid.geo_utils import (
    load_malawi_district_geojson as _load_malawi_district_geojson,
    build_geo_reference as _build_geo_reference,
    derive_facility_positions as _derive_facility_positions,
)


_CHART_LAYOUT = dict(
    paper_bgcolor=BG, plot_bgcolor=BG,
    font=dict(family=FONT, color=TEXT, size=11),
    margin=dict(l=4, r=4, t=36, b=4),
    hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
    legend=dict(font=dict(size=10, color=DIM), bgcolor='rgba(0,0,0,0)',
                orientation='v', x=1.02, y=0.5, xanchor='left'),
)

_TREND_SERIES_PALETTE = [
    '#2563EB', '#0F766E', '#C2410C', '#7C3AED',
    '#DB2777', '#0891B2', '#4D7C0F', '#B45309',
    '#1D4ED8', '#BE185D', '#0F766E', '#6D28D9',
]
_TREND_ACCENT = {
    'ANC': '#2563EB',
    'Labour': '#C2410C',
    'Newborn': '#0F766E',
    'PNC': '#7C3AED',
}
_ANALYSIS_PALETTE = ['#2563EB', '#0F766E', '#7C3AED', '#C2410C', '#DB2777', '#0891B2', '#64748B']

# MNID data helpers

def _cov(df, n_cfg, d_cfg):
    try:   num = int(create_count_from_config(df, n_cfg) or 0)
    except: num = 0
    try:   den = int(create_count_from_config(df, d_cfg) or 0)
    except: den = 0
    pct = round(num / den * 100, 1) if den else 0.0
    return num, den, pct


def _monthly(df, n_cfg, d_cfg, n=6):
    if 'Date' not in df.columns or not len(df): return []
    try:
        d2 = df.copy()
        d2['_m'] = pd.to_datetime(d2['Date']).dt.to_period('M')
        months = sorted(d2['_m'].unique())[-n:]
        return [{'x': datetime(m.year, m.month, 1),
                 'pct': _cov(d2[d2['_m'] == m], n_cfg, d_cfg)[2]}
                for m in months]
    except: return []


def _css(pct, tgt): return 'ok' if pct>=tgt else ('warn' if pct>=tgt*0.85 else 'danger')
_CLR = {'ok': OK_C, 'warn': WARN_C, 'danger': DANGER_C, 'info': INFO_C}


def _display_pct(pct):
    if pct is None:
        return None
    return max(0.0, min(float(pct), 100.0))


def _axis_wrap(label: str, width: int = 14, max_lines: int = 3) -> str:
    words = str(label or '').split()
    if not words:
        return ''
    lines = []
    current = words[0]
    used = 1
    for word in words[1:]:
        if len(current) + len(word) + 1 <= width:
            current = f'{current} {word}'
        else:
            lines.append(current)
            current = word
        used += 1
        if len(lines) >= max_lines - 1:
            break
    remaining = words[used:]
    if remaining:
        current = f'{current} {" ".join(remaining)}'.strip()
    lines.append(current)
    if len(lines[-1]) > width + 4:
        lines[-1] = f'{lines[-1][:width + 1].rstrip()}...'
    return '<br>'.join(lines)


def _infer_facility_type(facility_key: str) -> str:
    fac_code = str(facility_key or '').rstrip('*')
    name = _FACILITY_NAMES.get(fac_code, fac_code).strip()
    upper = name.upper()
    if 'CENTRAL' in upper or upper.endswith(' CH'):
        return 'Central Hospital'
    if 'HEALTH CENT' in upper or upper.endswith(' HC'):
        return 'Health Center'
    if 'DISTRICT' in upper or 'HOSPITAL' in upper:
        return 'District Hospital'
    return 'Other'


def _contrast_text(hex_color: str, dark: str = TEXT, light: str = '#FFFFFF') -> str:
    color = (hex_color or '').lstrip('#')
    if len(color) != 6:
        return dark
    r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return dark if luminance > 0.62 else light


def _value_counts(df, concept, col='obs_value_coded', unique_col='person_id'):
    sub = df[df['concept_name'] == concept]
    if not len(sub): return pd.DataFrame(columns=['label','n'])
    out = sub.groupby(col)[unique_col].nunique().reset_index()
    out.columns = ['label','n']
    return out.sort_values('n', ascending=False)


def _monthly_visits(df, encounter_val, unique_col='person_id'):
    sub = df[df['Encounter'] == encounter_val].copy() if 'Encounter' in df.columns else pd.DataFrame()
    if not len(sub): return pd.DataFrame(columns=['month','n'])
    sub['month'] = pd.to_datetime(sub['Date']).dt.to_period('M')
    out = sub.groupby('month')[unique_col].nunique().reset_index()
    out.columns = ['month','n']
    out['month'] = out['month'].apply(lambda m: datetime(m.year, m.month, 1))
    return out


# MNID chart builders

def _empty_card(title):
    return html.Div(className='mnid-chart-card', children=[
        html.Div(title, className='mnid-card-title'),
        html.Div('No data available', className='mnid-ind-note',
                 style={'padding': '24px 0', 'textAlign': 'center'}),
    ])


def _chart_card(title, fig):
    return html.Div(className='mnid-chart-card', children=[
        dcc.Graph(figure=fig, config={'displayModeBar': True, 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                  style={'height': '220px'}),
    ])


def _donut(counts_df, title, color_map=None):
    if not len(counts_df):
        return None
    palette = _ANALYSIS_PALETTE
    colors = [color_map.get(r, palette[i % len(palette)])
              if color_map else palette[i % len(palette)]
              for i, r in enumerate(counts_df['label'])]
    fig = go.Figure(go.Pie(
        labels=counts_df['label'], values=counts_df['n'],
        hole=0.62,
        marker=dict(colors=colors, line=dict(color='#fff', width=2)),
        textinfo='none',
        hovertemplate='%{label}<br>%{value} (%{percent})<extra></extra>',
    ))
    fig.update_layout(
        **_CHART_LAYOUT,
        title=dict(text=title, font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.98),
        height=220,
    )
    return fig


def _hbar(counts_df, title, color=INFO_C, single_color=False):
    if not len(counts_df):
        return None
    counts_df = counts_df.sort_values('n')
    palette = _ANALYSIS_PALETTE
    colors = color if single_color else [palette[i % len(palette)]
                                         for i in range(len(counts_df))]
    fig = go.Figure(go.Bar(
        x=counts_df['n'], y=counts_df['label'],
        orientation='h',
        marker=dict(color=colors, line=dict(color='rgba(0,0,0,0)')),
        text=counts_df['n'], textposition='outside',
        textfont=dict(size=10, color=DIM),
        hovertemplate='%{y}: %{x}<extra></extra>',
    ))
    fig.update_layout(
        **_CHART_LAYOUT,
        title=dict(text=title, font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.98),
        height=220,
        xaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False,
                   showline=False, tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=DIM), automargin=True),
    )
    return fig


def _line(monthly_df, title, color='#2563EB', y_label='Clients'):
    if not len(monthly_df): return None
    fig = go.Figure(go.Scatter(
        x=monthly_df['month'], y=monthly_df['n'],
        mode='lines+markers',
        line=dict(color=color, width=2.25, shape='spline'),
        marker=dict(size=5, color=color, line=dict(color='#fff', width=1.25)),
        hovertemplate='%{x|%b %Y}: %{y}<extra></extra>',
    ))
    fig.update_layout(
        **_CHART_LAYOUT,
        title=dict(text=title, font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.98),
        height=220,
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickformat='%b %y', tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False,
                   showline=False, tickfont=dict(size=10, color=MUTED),
                   title=dict(text=y_label, font=dict(size=10, color=MUTED))),
    )
    return fig


# MNID trend switcher

_CAT_LABELS = {'ANC': 'ANC', 'Labour': 'Labour & Delivery', 'Newborn': 'Newborn', 'PNC': 'PNC'}
_CAT_ORDER  = ['ANC', 'Labour', 'Newborn', 'PNC']


def _resolve_category_order(indicators: list, configured: list | None = None) -> list:
    present = {str(i.get('category', '')).strip() for i in indicators if i.get('category')}
    ordered = [c for c in (configured or _CAT_ORDER) if c in present]
    return ordered or [c for c in _CAT_ORDER if c in present]


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
    d2 = df.copy()
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

        has_data = any(y is not None for y in ys)
        if not has_data:
            if chart_type == 'bar':
                fig.add_trace(go.Bar(x=[], y=[], name=ind['label'], marker=dict(color=c), showlegend=True))
            else:
                fig.add_trace(go.Scatter(x=[], y=[], name=ind['label'], line=dict(color=c), showlegend=True))
            continue

        if chart_type == 'bar':
            clean_xs = [x for x, y in zip(xs, ys) if y is not None]
            clean_ys = [y for y in ys if y is not None]
            fig.add_trace(go.Bar(
                x=clean_xs, y=clean_ys, name=ind['label'],
                marker=dict(color=f'rgba({r},{g},{b},0.85)', line=dict(color=c, width=1)),
                hovertemplate=f'%{{x|%b %Y}}<br>{ind["label"]}: %{{y:.0f}}%<extra></extra>',
                offsetgroup=str(j),
            ))
        else:
            fig.add_trace(go.Scatter(
                x=xs, y=ys, name=ind['label'],
                mode='lines+markers',
                line=dict(color=c, width=2, shape='spline'),
                marker=dict(size=5, color=c, line=dict(color='#fff', width=1.25)),
                connectgaps=True,
                hovertemplate=f'%{{x|%b %Y}}<br>{ind["label"]}: %{{y:.0f}}%<extra></extra>',
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
    Output('mnid-trend-graph', 'figure'),
    Output('mnid-trend-active-cat', 'data'),
    Output({'type': 'trend-cat-btn', 'index': ALL}, 'className'),
    Output('mnid-trend-indicators', 'options'),
    Output('mnid-trend-indicators', 'value'),
    Output('mnid-trend-chart-type-store', 'data'),
    Output('mnid-trend-chart-toggle', 'className'),
    Output('mnid-trend-chart-toggle-text', 'children'),
    Input({'type': 'trend-cat-btn', 'index': ALL}, 'n_clicks'),
    Input('mnid-trend-chart-toggle', 'n_clicks'),
    Input('mnid-trend-indicators', 'value'),
    State('mnid-trend-store', 'data'),
    State('mnid-trend-active-cat', 'data'),
    State('mnid-trend-chart-type-store', 'data'),
    State('mnid-trend-cats-store', 'data'),
    prevent_initial_call=False,
)
def update_trend_chart(n_clicks_list, toggle_clicks, selected_ind_ids, stored_trend, active_cat, chart_type, cat_order):
    categories = cat_order or _CAT_ORDER
    cat = active_cat if active_cat in categories else (categories[0] if categories else 'ANC')
    mode = chart_type or 'line'
    selected_ind_ids = selected_ind_ids or []
    ctx = callback_context
    if ctx and ctx.triggered:
        prop_id = ctx.triggered[0]['prop_id']
        if 'trend-cat-btn' in prop_id:
            try:
                next_cat = json.loads(prop_id.split('.')[0]).get('index', cat)
                if next_cat in categories:
                    cat = next_cat
            except Exception:
                pass
        elif prop_id == 'mnid-trend-chart-toggle.n_clicks':
            mode = 'bar' if mode == 'line' else 'line'
            selected_ind_ids = []

    trend_payload = stored_trend or {}
    tracked = trend_payload.get('tracked', [])
    df = _deserialize_store_df(trend_payload.get('records'))
    scope_meta = trend_payload.get('scope_meta') or {}
    cat_inds = [i for i in tracked if i.get('category') == cat and i.get('status') == 'tracked']
    ind_options = [{'label': i['label'], 'value': i['id']} for i in cat_inds]
    valid_ids = [opt['value'] for opt in ind_options]
    selected = [iid for iid in selected_ind_ids if iid in valid_ids][:3]
    if not selected:
        selected = valid_ids[:3]
    active_inds = [i for i in cat_inds if i['id'] in selected]
    fig = _location_trend_fig(df, active_inds, cat, mode, scope_meta)

    classes = [
        'mnid-filter-btn active' if c == cat else 'mnid-filter-btn'
        for c in categories
    ]
    toggle_class = 'mnid-trend-toggle is-bar' if mode == 'bar' else 'mnid-trend-toggle is-line'
    toggle_text = 'Bar' if mode == 'bar' else 'Line'
    return fig, cat, classes, ind_options, selected, mode, toggle_class, toggle_text


def _trend_switcher(df: pd.DataFrame, indicators: list, categories: list | None = None,
                    default_cat: str | None = None,
                    scope_meta: dict | None = None) -> html.Div:
    tracked = [i for i in indicators if i.get('status') == 'tracked']
    cat_order = _resolve_category_order(tracked, categories)
    default_cat = default_cat if default_cat in cat_order else (cat_order[0] if cat_order else 'ANC')
    default_inds = [i for i in tracked if i.get('category') == default_cat][:3]
    default_ind_opts = [{'label': i['label'], 'value': i['id']} for i in tracked if i.get('category') == default_cat]
    default_fig = _location_trend_fig(df, default_inds, default_cat, 'line', scope_meta)
    trend_store = {
        'tracked': tracked,
        'records': _serialize_store_df(df),
        'scope_meta': scope_meta or {},
    }

    return html.Div(className='mnid-card', style={'marginBottom': '12px'}, children=[
        html.Div(style={'display': 'flex', 'alignItems': 'center',
                        'justifyContent': 'space-between', 'marginBottom': '8px', 'gap': '12px', 'flexWrap': 'wrap'}, children=[
            html.Div('COVERAGE TREND BY LOCATION', className='mnid-section-lbl',
                     style={'marginBottom': '0'}),
            html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'flexWrap': 'wrap'}, children=[
                html.Button(
                    id='mnid-trend-chart-toggle',
                    className='mnid-trend-toggle is-line',
                    n_clicks=0,
                    type='button',
                    children=[
                        html.Span('Line', id='mnid-trend-chart-toggle-text', className='mnid-trend-toggle-text'),
                        html.Span(className='mnid-trend-toggle-thumb'),
                    ],
                ),
                html.Div(className='mnid-filter-row', children=[
                    html.Button(
                        _CAT_LABELS.get(c, c),
                        id={'type': 'trend-cat-btn', 'index': c},
                        className='mnid-filter-btn' + (' active' if c == default_cat else ''),
                        n_clicks=0,
                    )
                    for c in cat_order
                ]),
            ]),
        ]),
        html.Div(style={'marginBottom': '8px', 'maxWidth': '360px'}, children=[
            html.Div('Indicators', style={'fontSize': '10px', 'color': MUTED, 'fontWeight': '600', 'marginBottom': '3px'}),
            dcc.Dropdown(
                id='mnid-trend-indicators',
                options=default_ind_opts,
                value=[i['id'] for i in default_inds],
                multi=True,
                placeholder='Select up to 3 indicators...',
                style={'fontSize': '12px', 'minHeight': '34px'},
            ),
        ]),
        dcc.Store(id='mnid-trend-store', data=trend_store),
        dcc.Store(id='mnid-trend-active-cat', data=default_cat),
        dcc.Store(id='mnid-trend-cats-store', data=cat_order),
        dcc.Store(id='mnid-trend-chart-type-store', data='line'),
        dcc.Graph(id='mnid-trend-graph', figure=default_fig,
                  config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}}, style={'height': '340px'}),
    ])


def _encounter_slice(df: pd.DataFrame, regex: str) -> pd.DataFrame:
    if df is None or df.empty or 'Encounter' not in df.columns:
        return pd.DataFrame()
    enc = df['Encounter'].fillna('').astype(str)
    return df[enc.str.contains(regex, case=False, na=False)].copy()


def _count_entities(df: pd.DataFrame, col: str) -> int:
    if df is None or df.empty or col not in df.columns:
        return 0
    return int(df[col].dropna().astype(str).nunique())


def _concept_count(df: pd.DataFrame, concept: str, values=None,
                   col: str = 'obs_value_coded', any_value: bool = False) -> int:
    if df is None or df.empty or 'concept_name' not in df.columns:
        return 0
    sub = df[df['concept_name'].fillna('').astype(str) == concept].copy()
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
        for candidate in [col, 'obs_value_coded', 'Value', 'Value_Name']:
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
                fac_df = fac_df.copy()
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
                ('ANC visits recorded', lambda x: _count_entities(x, 'encounter_id')),
                ('Unique ANC clients', lambda x: _count_entities(x, 'person_id')),
                ('Repeat ANC contact volume', lambda x: max(_count_entities(x, 'encounter_id') - _count_entities(x, 'person_id'), 0)),
                ('Gestational age recorded', lambda x: _concept_count(x, 'Gestational age recorded', any_value=True)),
                ('Blood group recorded', lambda x: _concept_count(x, 'Blood group rhesus factor', any_value=True)),
                ('Pregnancy planned responses', lambda x: _concept_count(x, 'Pregnancy planned', any_value=True)),
                ('HIV test results recorded', lambda x: _concept_count(x, 'HIV Test', any_value=True)),
                ('Reactive HIV results', lambda x: _concept_count(x, 'HIV Test', ['Reactive'])),
                ('ITNs given', lambda x: _concept_count(x, 'Insecticide treated net given', ['Yes', 'Given'])),
                ('2+ tetanus doses recorded', lambda x: _concept_count(x, 'Number of tetanus doses', ['two doses', 'three doses', 'four doses'])),
            ],
            'chart_specs': [
                {
                    'id': 'anc_hiv_testing',
                    'label': 'HIV Testing',
                    'title': 'HIV Testing in ANC',
                    'total_metric': 'HIV test results recorded',
                    'segments': [
                        {'label': 'Reactive', 'metric': 'Reactive HIV results', 'color': '#DB2777'},
                    ],
                    'remainder_label': 'Screened non-reactive / other',
                    'remainder_color': '#2563EB',
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
                    'id': 'anc_blood_group',
                    'label': 'Blood Group',
                    'title': 'Blood Group Documentation',
                    'total_metric': 'Unique ANC clients',
                    'segments': [
                        {'label': 'Blood group recorded', 'metric': 'Blood group recorded', 'color': '#7C3AED'},
                    ],
                    'remainder_label': 'Missing blood group',
                    'remainder_color': '#CBD5E1',
                },
            ],
        },
        'Labour': {
            'title': 'Labour & Delivery Summary',
            'subtitle': 'Facility rows with labour and delivery indicators as columns.',
            'encounter': 'LABOUR|DELIVERY|BIRTH',
            'metrics': [
                ('Deliveries recorded', lambda x: _count_entities(x, 'encounter_id')),
                ('Unique mothers', lambda x: _count_entities(x, 'person_id')),
                ('Live births', lambda x: _concept_count(x, 'Outcome of the delivery', ['Live birth', 'Live births'])),
                ('Stillbirths', lambda x: _concept_count(x, 'Outcome of the delivery', ['Stillbirth', 'Fresh stillbirth', 'Macerated stillbirth'])),
                ('Twin deliveries', lambda x: _concept_count(x, 'Outcome of the delivery', ['Twin delivery'])),
                ('Mothers referred', lambda x: _concept_count(x, 'Referral completed', ['Yes'])),
                ('Referral reasons captured', lambda x: _concept_count(x, 'referral reasons', any_value=True)),
                ('Newborn complications recorded', lambda x: _concept_count(x, 'Newborn baby complications', any_value=True)),
                ('Newborn management recorded', lambda x: _concept_count(x, 'Management given to newborn', any_value=True)),
                ('Birth attendant recorded', lambda x: _concept_count(x, 'Staff conducting delivery', any_value=True)),
            ],
            'chart_specs': [
                {
                    'id': 'labour_birth_outcomes',
                    'label': 'Birth Outcomes',
                    'title': 'Delivery Outcomes',
                    'total_metric': 'Deliveries recorded',
                    'segments': [
                        {'label': 'Live births', 'metric': 'Live births', 'color': '#0F766E'},
                        {'label': 'Stillbirths', 'metric': 'Stillbirths', 'color': '#DB2777'},
                    ],
                    'remainder_label': 'Other / uncategorized outcomes',
                    'remainder_color': '#CBD5E1',
                },
                {
                    'id': 'labour_referrals',
                    'label': 'Referral Flow',
                    'title': 'Delivery Referrals',
                    'total_metric': 'Unique mothers',
                    'segments': [
                        {'label': 'Mothers referred', 'metric': 'Mothers referred', 'color': '#C2410C'},
                    ],
                    'remainder_label': 'Managed without referral',
                    'remainder_color': '#94A3B8',
                },
            ],
        },
        'Newborn': {
            'title': 'Newborn Summary',
            'subtitle': 'Facility rows with newborn care indicators as columns.',
            'encounter': 'NEONATAL',
            'metrics': [
                ('Admissions recorded', lambda x: _count_entities(x, 'encounter_id')),
                ('Unique babies', lambda x: _count_entities(x, 'person_id')),
                ('Repeat admission / review volume', lambda x: max(_count_entities(x, 'encounter_id') - _count_entities(x, 'person_id'), 0)),
                ('Resuscitation provided', lambda x: _concept_count(x, 'Neonatal resuscitation provided', ['Yes', 'Stimulation only', 'Bag and mask'])),
                ('Resuscitation not required', lambda x: _concept_count(x, 'Neonatal resuscitation provided', ['Not required'])),
                ('Not hypothermic on admission', lambda x: _concept_count(x, 'Thermal status on admission', ['Not hypothermic'])),
                ('Hypothermia on admission', lambda x: _concept_count(x, 'Thermal status on admission', ['Mild hypothermia', 'Moderate hypothermia', 'Severe hypothermia'])),
                ('Bubble CPAP support', lambda x: _concept_count(x, 'CPAP support', ['Bubble CPAP'])),
                ('Nasal oxygen support', lambda x: _concept_count(x, 'CPAP support', ['Nasal oxygen'])),
                ('Phototherapy given', lambda x: _concept_count(x, 'Phototherapy given', ['Yes'])),
                ('Parenteral antibiotics given', lambda x: _concept_count(x, 'Parenteral antibiotics given', ['Yes'])),
                ('iKMC initiated', lambda x: _concept_count(x, 'iKMC initiated', ['Yes'])),
            ],
            'chart_specs': [
                {
                    'id': 'newborn_thermal_status',
                    'label': 'Thermal Status',
                    'title': 'Thermal Status on Admission',
                    'segments': [
                        {'label': 'Not hypothermic', 'metric': 'Not hypothermic on admission', 'color': '#2563EB'},
                        {'label': 'Hypothermia', 'metric': 'Hypothermia on admission', 'color': '#DB2777'},
                    ],
                },
                {
                    'id': 'newborn_resuscitation',
                    'label': 'Resuscitation',
                    'title': 'Newborn Resuscitation Response',
                    'total_metric': 'Unique babies',
                    'segments': [
                        {'label': 'Resuscitation provided', 'metric': 'Resuscitation provided', 'color': '#0F766E'},
                        {'label': 'Not required', 'metric': 'Resuscitation not required', 'color': '#2563EB'},
                    ],
                    'remainder_label': 'Other / no response recorded',
                    'remainder_color': '#CBD5E1',
                },
                {
                    'id': 'newborn_respiratory_support',
                    'label': 'Respiratory Support',
                    'title': 'Respiratory Support Mix',
                    'total_metric': 'Unique babies',
                    'segments': [
                        {'label': 'Bubble CPAP', 'metric': 'Bubble CPAP support', 'color': '#7C3AED'},
                        {'label': 'Nasal oxygen', 'metric': 'Nasal oxygen support', 'color': '#0891B2'},
                    ],
                    'remainder_label': 'No advanced support tracked',
                    'remainder_color': '#CBD5E1',
                },
            ],
        },
        'PNC': {
            'title': 'PNC Summary',
            'subtitle': 'Facility rows with postnatal care indicators as columns.',
            'encounter': 'PNC|POSTNATAL|POST.NATAL',
            'metrics': [
                ('PNC visits recorded', lambda x: _count_entities(x, 'encounter_id')),
                ('Unique mothers', lambda x: _count_entities(x, 'person_id')),
                ('Babies reviewed', lambda x: _concept_count(x, 'Status of baby', any_value=True)),
                ('Maternal deaths', lambda x: _concept_count(x, 'Status of the mother', ['Death', 'Died'])),
                ('Maternal referrals', lambda x: _concept_count(x, 'Status of the mother', ['Referred'])),
                ('Baby deaths', lambda x: _concept_count(x, 'Status of baby', ['Death', 'Died'])),
                ('Baby referrals', lambda x: _concept_count(x, 'Status of baby', ['Referred'])),
                ('Mother HIV status captured', lambda x: _concept_count(x, 'Mother HIV Status', any_value=True)),
                ('Vitamin K given', lambda x: _concept_count(x, 'Vitamin K given', ['Yes'])),
                ('Immunisation recorded', lambda x: _concept_count(x, 'Immunisation given', any_value=True) + _concept_count(x, 'Type of immunization the baby received', any_value=True)),
            ],
            'chart_specs': [
                {
                    'id': 'pnc_maternal_outcomes',
                    'label': 'Maternal Outcomes',
                    'title': 'Maternal PNC Outcomes',
                    'total_metric': 'Unique mothers',
                    'segments': [
                        {'label': 'Maternal referrals', 'metric': 'Maternal referrals', 'color': '#C2410C'},
                        {'label': 'Maternal deaths', 'metric': 'Maternal deaths', 'color': '#DB2777'},
                    ],
                    'remainder_label': 'Stable / other outcomes',
                    'remainder_color': '#CBD5E1',
                },
                {
                    'id': 'pnc_baby_outcomes',
                    'label': 'Baby Outcomes',
                    'title': 'Baby Outcomes During PNC',
                    'total_metric': 'Babies reviewed',
                    'segments': [
                        {'label': 'Baby referrals', 'metric': 'Baby referrals', 'color': '#C2410C'},
                        {'label': 'Baby deaths', 'metric': 'Baby deaths', 'color': '#DB2777'},
                    ],
                    'remainder_label': 'Stable / other outcomes',
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


def _monthly_concept_rate(df, concept, positive_values=None, title='', target=None,
                          color='#2563EB', target_col='obs_value_coded'):
    if df is None or df.empty or 'Date' not in df.columns or 'concept_name' not in df.columns:
        return None
    sub = df[df['concept_name'].fillna('').astype(str) == concept].copy()
    if sub.empty:
        return None
    col = target_col if target_col in sub.columns else ('obs_value_coded' if 'obs_value_coded' in sub.columns else None)
    if not col:
        return None

    sub['_m'] = pd.to_datetime(sub['Date']).dt.to_period('M')
    months = sorted(sub['_m'].dropna().unique())[-12:]
    if not months:
        return None

    xs = [pd.Period(m, 'M').to_timestamp().to_pydatetime() for m in months]
    ys = []
    for m in months:
        month_df = sub[sub['_m'] == m].copy()
        den = month_df['person_id'].dropna().astype(str).nunique() if 'person_id' in month_df.columns else len(month_df)
        if den <= 0:
            ys.append(None)
            continue
        if positive_values is None:
            num = den
        else:
            wanted = {str(v).strip().lower() for v in positive_values}
            series = month_df[col].fillna('').astype(str).str.strip().str.lower()
            num = month_df[series.isin(wanted)]['person_id'].dropna().astype(str).nunique() if 'person_id' in month_df.columns else int(series.isin(wanted).sum())
        ys.append(round((num / den) * 100, 1) if den else None)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode='lines+markers',
        line=dict(color=color, width=2.2, shape='spline'),
        marker=dict(size=5, color=color, line=dict(color='#fff', width=1)),
        connectgaps=False,
        hovertemplate='%{x|%b %Y}<br>%{y:.0f}%<extra></extra>',
        showlegend=False,
    ))
    if target is not None:
        fig.add_trace(go.Scatter(
            x=xs, y=[target] * len(xs),
            mode='lines',
            line=dict(color='#A1A1AA', width=1.5, dash='dash'),
            hovertemplate='Target: %{y:.0f}%<extra></extra>',
            showlegend=False,
        ))
    fig.update_layout(
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        font=dict(family=FONT, color=TEXT, size=11),
        margin=dict(l=12, r=8, t=28, b=26),
        height=210,
        title=dict(text=title, x=0, xanchor='left', font=dict(size=12, color='#444441', family=FONT)),
        xaxis=dict(showgrid=False, zeroline=False, showline=False, tickformat='%b %y',
                   tickfont=dict(size=9, color=MUTED)),
        yaxis=dict(range=[0, 100], showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=9, color=MUTED), ticksuffix='%',
                   title=dict(text='Coverage', font=dict(size=9, color=MUTED))),
    )
    return fig


def _monthly_concept_mix_fig(df, concept, categories, title, target_col='obs_value_coded'):
    if df is None or df.empty or 'Date' not in df.columns or 'concept_name' not in df.columns:
        return None
    sub = df[df['concept_name'].fillna('').astype(str) == concept].copy()
    if sub.empty:
        return None
    col = target_col if target_col in sub.columns else ('obs_value_coded' if 'obs_value_coded' in sub.columns else None)
    if not col:
        return None

    sub['_m'] = pd.to_datetime(sub['Date']).dt.to_period('M')
    months = sorted(sub['_m'].dropna().unique())[-12:]
    if not months:
        return None

    fig = go.Figure()
    for label, values, color in categories:
        vals = []
        wanted = {str(v).strip().lower() for v in values}
        for m in months:
            month_df = sub[sub['_m'] == m].copy()
            den = month_df['person_id'].dropna().astype(str).nunique() if 'person_id' in month_df.columns else len(month_df)
            if den <= 0:
                vals.append(0)
                continue
            series = month_df[col].fillna('').astype(str).str.strip().str.lower()
            num = month_df[series.isin(wanted)]['person_id'].dropna().astype(str).nunique() if 'person_id' in month_df.columns else int(series.isin(wanted).sum())
            vals.append(round((num / den) * 100, 1))
        fig.add_trace(go.Bar(
            x=[pd.Period(m, 'M').to_timestamp().to_pydatetime() for m in months],
            y=vals,
            name=label,
            marker=dict(color=color),
            hovertemplate='%{x|%b %Y}<br>' + label + ': %{y:.0f}%<extra></extra>',
        ))
    fig.update_layout(
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        font=dict(family=FONT, color=TEXT, size=11),
        margin=dict(l=12, r=8, t=30, b=28),
        height=240,
        title=dict(text=title, x=0, xanchor='left', font=dict(size=12, color='#444441', family=FONT)),
        barmode='stack',
        legend=dict(orientation='h', x=0, y=1.14, xanchor='left', font=dict(size=9, color=DIM)),
        xaxis=dict(showgrid=False, zeroline=False, showline=False, tickformat='%b %y',
                   tickfont=dict(size=9, color=MUTED)),
        yaxis=dict(range=[0, 100], showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=9, color=MUTED), ticksuffix='%',
                   title=dict(text='Share of babies', font=dict(size=9, color=MUTED))),
    )
    return fig


def _concept_rate(df, concept, positive_values=None, target_col='obs_value_coded'):
    if df is None or df.empty or 'concept_name' not in df.columns:
        return 0, 0, 0.0
    sub = df[df['concept_name'].fillna('').astype(str) == concept].copy()
    if sub.empty:
        return 0, 0, 0.0
    den = sub['person_id'].dropna().astype(str).nunique() if 'person_id' in sub.columns else len(sub)
    if den <= 0:
        return 0, 0, 0.0
    if positive_values is None:
        return den, den, 100.0
    col = target_col if target_col in sub.columns else ('obs_value_coded' if 'obs_value_coded' in sub.columns else None)
    if not col:
        return 0, den, 0.0
    wanted = {str(v).strip().lower() for v in positive_values}
    series = sub[col].fillna('').astype(str).str.strip().str.lower()
    num = sub[series.isin(wanted)]['person_id'].dropna().astype(str).nunique() if 'person_id' in sub.columns else int(series.isin(wanted).sum())
    pct = round((num / den) * 100, 1) if den else 0.0
    return num, den, pct


def _newborn_summary_card(label, num, den, pct, accent, note):
    return html.Div(className='mnid-newborn-metric', style={'--nb-accent': accent}, children=[
        html.Div(label, className='mnid-newborn-metric-label'),
        html.Div([
            html.Span(f'{_display_pct(pct):.0f}%', className='mnid-newborn-metric-value'),
            html.Span(f'{num}/{den}', className='mnid-newborn-metric-meta'),
        ], className='mnid-newborn-metric-top'),
        html.Div(note, className='mnid-newborn-metric-note'),
    ])


def _newborn_section_card(title, subtitle, tone, children):
    return html.Div(className=f'mnid-chart-card mnid-newborn-section mnid-newborn-{tone}',
                    style={'gridColumn': '1 / -1'},
                    children=[
                        html.Div(className='mnid-newborn-section-head', children=[
                            html.Div([
                                html.Div(title, className='mnid-card-title'),
                                html.Div(subtitle, className='mnid-newborn-section-subtitle'),
                            ]),
                            html.Span(tone.upper(), className='mnid-newborn-section-tag'),
                        ]),
                        children,
                    ])


def _first_available_value_counts(df: pd.DataFrame, concepts: list[str], col: str = 'obs_value_coded'):
    for concept in concepts:
        vc = _value_counts(df, concept, col=col)
        if len(vc):
            return vc, concept
    return pd.DataFrame(columns=['label', 'n']), None


def _newborn_tab_content(desc: str, children: list):
    cards = [child for child in children if child is not None]
    if not cards:
        cards = [_no_data_card('No data available for this module.')]
    return html.Div(className='mnid-newborn-tab-panel', children=[
        html.Div(desc, className='mnid-newborn-tab-desc'),
        html.Div(className='mnid-newborn-subgrid mnid-newborn-subgrid-3', children=cards),
    ])


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

    scope_meta = scope_meta or {}
    selected_facs = [str(v) for v in (scope_meta.get('selected_facilities') or [])]
    selected_dists = [str(v) for v in (scope_meta.get('selected_districts') or [])]
    level = str(scope_meta.get('level') or '')

    d2 = df.copy()
    d2['_m'] = pd.to_datetime(d2['Date']).dt.to_period('M')
    periods = sorted(d2['_m'].dropna().unique())[-12:]

    facility_name_map = {}
    if 'Facility_CODE' in d2.columns:
        for fac_code, fac_df in d2.groupby('Facility_CODE', dropna=True):
            fac_name = _FACILITY_NAMES.get(str(fac_code), str(fac_code))
            if 'Facility' in fac_df.columns:
                names = fac_df['Facility'].dropna().astype(str)
                if not names.empty:
                    fac_name = names.mode().iloc[0]
            facility_name_map[str(fac_code)] = fac_name

    entity_mode = 'district'
    entities = []
    if selected_facs and 'Facility_CODE' in d2.columns:
        entity_mode = 'facility'
        entities = selected_facs[:6]
    elif selected_dists and 'District' in d2.columns:
        entities = selected_dists[:6]
    elif level == 'Facility' and 'Facility_CODE' in d2.columns:
        entity_mode = 'facility'
        entities = d2['Facility_CODE'].dropna().astype(str).value_counts().index.tolist()[:6]
    elif 'District' in d2.columns:
        entities = d2['District'].dropna().astype(str).value_counts().index.tolist()[:6]
    elif 'Facility_CODE' in d2.columns:
        entity_mode = 'facility'
        entities = d2['Facility_CODE'].dropna().astype(str).value_counts().index.tolist()[:6]

    if not entities:
        fig.add_annotation(text='No locations available for trend view',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG,
                          height=340, margin=dict(l=8, r=8, t=12, b=24))
        return fig

    series_idx = 0
    for entity in entities:
        if entity_mode == 'facility':
            entity_df = d2[d2['Facility_CODE'].astype(str) == str(entity)].copy()
            entity_label = facility_name_map.get(str(entity), str(entity))
        else:
            entity_df = d2[d2['District'].astype(str) == str(entity)].copy()
            entity_label = str(entity)
        for ind in cat_inds:
            xs, ys = [], []
            for p in periods:
                month_df = entity_df[entity_df['_m'] == p]
                _, den, pct = _cov(month_df, ind['numerator_filters'], ind['denominator_filters'])
                xs.append(pd.Period(p, 'M').to_timestamp().to_pydatetime())
                ys.append(_display_pct(pct) if den > 0 else None)

            if not any(y is not None for y in ys):
                continue

            color = _TREND_SERIES_PALETTE[series_idx % len(_TREND_SERIES_PALETTE)]
            series_idx += 1
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            series_name = f'{entity_label} | {ind["label"]}'
            if chart_type == 'bar':
                clean_xs = [x for x, y in zip(xs, ys) if y is not None]
                clean_ys = [y for y in ys if y is not None]
                fig.add_trace(go.Bar(
                    x=clean_xs, y=clean_ys, name=series_name,
                    marker=dict(color=f'rgba({r},{g},{b},0.85)', line=dict(color=color, width=1)),
                    hovertemplate=f'%{{x|%b %Y}}<br>{series_name}: %{{y:.0f}}%<extra></extra>',
                    offsetgroup=str(series_idx),
                ))
            else:
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, name=series_name,
                    mode='lines+markers',
                    line=dict(color=color, width=2.3, shape='spline'),
                    marker=dict(size=5, color=color, line=dict(color='#fff', width=1.2)),
                    connectgaps=False,
                    hovertemplate=f'%{{x|%b %Y}}<br>{series_name}: %{{y:.0f}}%<extra></extra>',
                ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        height=340,
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


# HELPERS (vectorised coverage matrix)

def _mask(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """Build boolean row mask from a filter config dict without calling create_count."""
    mask = pd.Series(True, index=df.index)
    for i in range(1, 11):
        var = cfg.get(f'variable{i}')
        val = cfg.get(f'value{i}')
        if not var or not val:
            break
        if var not in df.columns:
            return pd.Series(False, index=df.index)
        mask &= df[var].isin(val) if isinstance(val, list) else (df[var] == val)
    return mask


def _matrix_by_group(df: pd.DataFrame, inds: list,
                     group_col: str, groups: list) -> list:
    """
    Vectorized: one groupby per indicator (not one filter per group x indicator).
    Returns z[indicator_idx][group_idx] = coverage % or None.
    """
    n_by_grp = {}
    d_by_grp = {}
    for ind in inds:
        nm = _mask(df, ind['numerator_filters'])
        dm = _mask(df, ind['denominator_filters'])
        n_by_grp[ind['id']] = df[nm].groupby(group_col)['person_id'].nunique().to_dict()
        d_by_grp[ind['id']] = df[dm].groupby(group_col)['person_id'].nunique().to_dict()

    z = []
    for ind in inds:
        row = []
        for g in groups:
            n = n_by_grp[ind['id']].get(g, 0)
            d = d_by_grp[ind['id']].get(g, 0)
            row.append(round(n / d * 100, 1) if d > 0 else None)
        z.append(row)
    return z


def _matrix_monthly(df: pd.DataFrame, inds: list) -> tuple:
    """Monthly view for a single facility. Returns (x_labels, z)."""
    d2 = df.copy()
    d2['_m'] = pd.to_datetime(d2['Date']).dt.to_period('M')
    periods = sorted(d2['_m'].dropna().unique())
    if not periods:
        return [], []

    x_labels = [f"{p.strftime('%b')} {str(p.year)[2:]}" for p in periods]
    n_by_m = {}
    d_by_m = {}
    for ind in inds:
        nm = _mask(d2, ind['numerator_filters'])
        dm = _mask(d2, ind['denominator_filters'])
        n_by_m[ind['id']] = d2[nm].groupby('_m')['person_id'].nunique().to_dict()
        d_by_m[ind['id']] = d2[dm].groupby('_m')['person_id'].nunique().to_dict()

    z = []
    for ind in inds:
        row = []
        for p in periods:
            n = n_by_m[ind['id']].get(p, 0)
            d = d_by_m[ind['id']].get(p, 0)
            row.append(round(n / d * 100, 1) if d > 0 else None)
        z.append(row)
    return x_labels, z


def _cov_color(pct):
    if pct is None: return '#E2E8F0'
    if pct >= 80:   return OK_C
    if pct >= 65:   return WARN_C
    return DANGER_C

# # MNID vectorized facility coverage computation

# MNID heatmap pre-computation

def _compute_heatmap_store(mch_full: pd.DataFrame, tracked: list,
                           facility_code: str) -> dict:
    """Pre-compute all view x year matrices into a JSON-serialisable store."""
    current_district = _FACILITY_DISTRICT.get(facility_code, '')
    if len(mch_full) and 'Facility_CODE' in mch_full.columns:
        all_facilities = sorted(mch_full['Facility_CODE'].dropna().astype(str).unique().tolist())
    else:
        all_facilities = sorted(_ALL_FACILITIES[:])

    geojson = _load_malawi_district_geojson()
    geo_districts = sorted({
        f.get('properties', {}).get('shapeName')
        for f in (geojson or {}).get('features', [])
        if f.get('properties', {}).get('shapeName')
    })
    if len(mch_full) and 'District' in mch_full.columns:
        data_districts = sorted(mch_full['District'].dropna().astype(str).unique().tolist())
    else:
        data_districts = sorted({
            _FACILITY_DISTRICT.get(f, '')
            for f in all_facilities
            if _FACILITY_DISTRICT.get(f)
        })
    all_districts = sorted(set(data_districts) | set(geo_districts) | set(_ALL_DISTRICTS))

    if facility_code and facility_code not in all_facilities:
        all_facilities.insert(0, facility_code)
    if current_district and current_district not in all_districts:
        all_districts.insert(0, current_district)

    sorted_inds = []
    for cat in ['ANC', 'Labour', 'Newborn', 'PNC']:
        sorted_inds.extend(i for i in tracked if i.get('category') == cat)
    sorted_inds.extend(i for i in tracked if i not in sorted_inds)

    y_labels  = [i['label'][:32] for i in sorted_inds]
    y_targets = [i['target']     for i in sorted_inds]

    store = {
        'y_labels': y_labels, 'y_targets': y_targets,
        'current_fac': facility_code, 'current_district': current_district,
        'all_facilities': all_facilities, 'all_districts': all_districts,
        'monthly': {}, 'by_facility': {}, 'by_district': {},
        'by_district_facs': {d: {} for d in all_districts},
        'yearly': {}, 'district_avgs': {},
    }

    if not len(mch_full) or not sorted_inds:
        return store

    years = []
    if 'Date' in mch_full.columns:
        years = sorted(mch_full['Date'].dt.year.dropna().astype(int).unique().tolist())
    year_options = {'All years': None, **{str(y): y for y in years}}
    district_facs_map = {
        d: [f for f in all_facilities if _FACILITY_DISTRICT.get(f) == d]
        for d in all_districts
    }
    store['facilities_by_district'] = district_facs_map

    for ylbl, yval in year_options.items():
        df = mch_full[mch_full['Date'].dt.year == yval].copy() if yval else mch_full.copy()
        if not len(df):
            for key in ['monthly', 'by_facility', 'by_district']:
                store[key][ylbl] = {'x': [], 'z': [], 'tick_angle': 0}
            for d in all_districts:
                store['by_district_facs'][d][ylbl] = {'x': [], 'z': [], 'tick_angle': -30}
            store['district_avgs'][ylbl] = {d: None for d in all_districts}
            continue

        # Monthly - current facility only
        fac_df = df[df['Facility_CODE'] == facility_code]
        if len(fac_df):
            x_m, z_m = _matrix_monthly(fac_df, sorted_inds)
        else:
            x_m, z_m = [], []
        store['monthly'][ylbl] = {'x': x_m, 'z': z_m, 'tick_angle': 0}

        # Vectorised groupby for facility and district - one pass per indicator
        n_by_fac  = {}; d_by_fac  = {}
        n_by_dist = {}; d_by_dist = {}
        has_dist  = 'District' in df.columns

        for ind in sorted_inds:
            nm = _mask(df, ind['numerator_filters'])
            dm = _mask(df, ind['denominator_filters'])
            n_by_fac[ind['id']]  = df[nm].groupby('Facility_CODE')['person_id'].nunique().to_dict()
            d_by_fac[ind['id']]  = df[dm].groupby('Facility_CODE')['person_id'].nunique().to_dict()
            if has_dist:
                n_by_dist[ind['id']] = df[nm].groupby('District')['person_id'].nunique().to_dict()
                d_by_dist[ind['id']] = df[dm].groupby('District')['person_id'].nunique().to_dict()

        def _cell(n_dict, d_dict, ind_id, key):
            n = n_dict.get(ind_id, {}).get(key, 0)
            d = d_dict.get(ind_id, {}).get(key, 0)
            return round(n / d * 100, 1) if d > 0 else None

        # All facilities
        x_f = [f'{f}*' if f == facility_code else f for f in all_facilities]
        z_f = [[_cell(n_by_fac, d_by_fac, ind['id'], fac) for fac in all_facilities]
               for ind in sorted_inds]
        store['by_facility'][ylbl] = {
            'x': x_f, 'z': z_f, 'tick_angle': -30,
            'districts': [_FACILITY_DISTRICT.get(f, '') for f in all_facilities],
        }

        # All districts
        if has_dist:
            data_districts = sorted(df['District'].dropna().unique().tolist())
            z_d = [[_cell(n_by_dist, d_by_dist, ind['id'], dist) for dist in data_districts]
                   for ind in sorted_inds]
            store['by_district'][ylbl] = {'x': data_districts[:], 'z': z_d, 'tick_angle': -20}
            d_avgs = {}
            for di, dist in enumerate(data_districts):
                vals = [z_d[ii][di] for ii in range(len(sorted_inds))
                        if ii < len(z_d) and di < len(z_d[ii]) and z_d[ii][di] is not None]
                d_avgs[dist] = round(sum(vals) / len(vals), 1) if vals else None
            store['district_avgs'][ylbl] = d_avgs
        else:
            store['by_district'][ylbl]   = {'x': [], 'z': [], 'tick_angle': -20}
            store['district_avgs'][ylbl] = {}

        # Per-district facility breakdowns
        for dist in all_districts:
            dfacs = district_facs_map[dist]
            x_df  = [f'{f}*' if f == facility_code else f for f in dfacs]
            z_df  = [[_cell(n_by_fac, d_by_fac, ind['id'], fac) for fac in dfacs]
                     for ind in sorted_inds]
            store['by_district_facs'][dist][ylbl] = {'x': x_df, 'z': z_df, 'tick_angle': -30}

    # Year-over-year for current facility
    fac_full = mch_full[mch_full['Facility_CODE'] == facility_code]
    if len(fac_full) and 'Date' in fac_full.columns:
        years = sorted(fac_full['Date'].dt.year.dropna().astype(int).unique().tolist())
        n_yr = {}; d_yr = {}
        for ind in sorted_inds:
            nm = _mask(fac_full, ind['numerator_filters'])
            dm = _mask(fac_full, ind['denominator_filters'])
            yr_col = fac_full['Date'].dt.year.astype(int)
            n_yr[ind['id']] = fac_full[nm].groupby(yr_col)['person_id'].nunique().to_dict()
            d_yr[ind['id']] = fac_full[dm].groupby(yr_col)['person_id'].nunique().to_dict()
        x_yr = [str(y) for y in years]
        z_yr  = [[round(n_yr[ind['id']].get(yr, 0) / d_yr[ind['id']].get(yr, 0) * 100, 1)
                  if d_yr[ind['id']].get(yr, 0) > 0 else None
                  for yr in years] for ind in sorted_inds]
        store['yearly'] = {'x': x_yr, 'z': z_yr, 'tick_angle': 0}

    # # MNID encounter volume counts for the right panel
    counts: dict = {}
    if 'Encounter' in mch_full.columns:
        enc_col = mch_full['Encounter'].fillna('').str.upper()
        fac_mask = mch_full['Facility_CODE'] == facility_code
        for ylbl, yval in {'All years': None, '2025': 2025, '2026': 2026}.items():
            if yval and 'Date' in mch_full.columns:
                yr_mask = mch_full['Date'].dt.year == yval
            else:
                yr_mask = pd.Series(True, index=mch_full.index)
            df_yr = mch_full[yr_mask & fac_mask]
            enc_yr = df_yr['Encounter'].fillna('').str.upper() if len(df_yr) else pd.Series(dtype=str)
            counts[ylbl] = {
                'ANC visits':   int(df_yr[enc_yr.str.contains('ANC',      na=False)]['person_id'].nunique()),
                'Deliveries':   int(df_yr[enc_yr.str.contains('LABOUR|DELIVERY|BIRTH', na=False)]['person_id'].nunique()),
                'PNC visits':   int(df_yr[enc_yr.str.contains('PNC|POSTNATAL|POST.NATAL', na=False)]['person_id'].nunique()),
                'All MCH encounters': int(df_yr['person_id'].nunique()),
            }
    store['counts'] = counts

    return store



def _build_facility_performance_heatmap_fig(stored: dict, year: str,
                                            district: str | None = None,
                                            sel_inds: list | None = None,
                                            facility_type: str | None = None) -> html.Div:
    all_labels = stored.get('y_labels', [])
    if sel_inds:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in sel_inds]
    else:
        rows_idx = list(range(len(all_labels)))

    focus_district = district or 'All'
    if focus_district == 'All':
        data = stored.get('by_facility', {}).get(year, {})
    else:
        data = stored.get('by_district_facs', {}).get(focus_district, {}).get(year, {})
    fac_keys = data.get('x', [])
    z_raw = data.get('z', [])

    selected_type = facility_type or 'All'
    facility_rows = []
    for col_idx, fac_key in enumerate(fac_keys):
        fac_code = str(fac_key or '').rstrip('*')
        fac_name = _FACILITY_NAMES.get(fac_code, fac_code)
        fac_kind = _infer_facility_type(fac_code)
        if selected_type != 'All' and fac_kind != selected_type:
            continue
        row_vals = [
            _display_pct(z_raw[row_idx][col_idx])
            if row_idx < len(z_raw) and col_idx < len(z_raw[row_idx]) and z_raw[row_idx][col_idx] is not None
            else None
            for row_idx in rows_idx
        ]
        vals = [v for v in row_vals if v is not None]
        avg = round(sum(vals) / len(vals), 1) if vals else None
        facility_rows.append({
            'facility': fac_name,
            'code': fac_code,
            'type': fac_kind,
            'avg': avg,
            'values': row_vals,
            'is_current': str(fac_code) == str(stored.get('current_fac', '')),
        })

    facility_rows = [r for r in facility_rows if any(v is not None for v in r['values'])]
    facility_rows.sort(key=lambda r: (r['avg'] is None, -(r['avg'] or 0), r['facility']))

    if not facility_rows or not rows_idx:
        return html.Div(
            'No facility comparison data for this selection',
            className='mnid-performance-table-empty',
        )

    def _header_cells(label: str) -> list:
        words = str(label or '').split()
        if not words:
            return ['-']
        lines = []
        current = words[0]
        for word in words[1:]:
            if len(current) + len(word) + 1 <= 16 and len(lines) < 2:
                current = f'{current} {word}'
            else:
                lines.append(current)
                current = word
                if len(lines) >= 2:
                    break
        remaining_words = words[len(' '.join(lines + [current]).split()):]
        if remaining_words:
            current = f"{current} {' '.join(remaining_words)}".strip()
        lines.append(current)
        if len(lines[-1]) > 16:
            lines[-1] = f"{lines[-1][:15].rstrip()}..."
        children = []
        for idx, line in enumerate(lines[:3]):
            if idx:
                children.append(html.Br())
            children.append(line)
        return children

    header_row = html.Tr([
        html.Th('Facility Name', className='mnid-performance-th mnid-performance-th-facility')
    ] + [
        html.Th(_header_cells(all_labels[i]), className='mnid-performance-th')
        for i in rows_idx
    ])

    body_rows = []
    for row in facility_rows:
        name = f"{row['facility']} *" if row['is_current'] else row['facility']
        cells = [html.Td(name, className='mnid-performance-facility-cell')]
        for val in row['values']:
            bg = '#E2E8F0' if val is None else _cov_color(val)
            fg = '#475569' if val is None else _contrast_text(bg)
            txt = '-' if val is None else f'{val:.0f}%'
            cells.append(html.Td(txt, className='mnid-performance-value-cell', style={
                'backgroundColor': bg,
                'color': fg,
            }))
        body_rows.append(html.Tr(cells))

    return html.Div(className='mnid-performance-table-wrap', children=[
        html.Table(className='mnid-performance-matrix', children=[
            html.Thead(header_row),
            html.Tbody(body_rows),
        ])
    ])


def _build_performance_attention_table(stored: dict, year: str,
                                       district: str | None = None,
                                       facility_type: str | None = None,
                                       sel_inds: list | None = None) -> html.Div:
    all_labels = stored.get('y_labels', [])
    all_targets = stored.get('y_targets', [])
    if sel_inds:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in sel_inds]
    else:
        rows_idx = list(range(len(all_labels)))

    focus_district = district or 'All'
    if focus_district == 'All':
        data = stored.get('by_facility', {}).get(year, {})
    else:
        data = stored.get('by_district_facs', {}).get(focus_district, {}).get(year, {})

    fac_keys = data.get('x', [])
    z_raw = data.get('z', [])
    selected_type = facility_type or 'All'

    rows = []
    for col_idx, fac_key in enumerate(fac_keys):
        fac_code = str(fac_key or '').rstrip('*')
        if str(fac_code) == str(stored.get('current_fac', '')):
            continue
        fac_name = _FACILITY_NAMES.get(fac_code, fac_code)
        fac_kind = _infer_facility_type(fac_code)
        if selected_type != 'All' and fac_kind != selected_type:
            continue

        values = []
        critical = []
        for row_idx in rows_idx:
            if row_idx >= len(z_raw) or col_idx >= len(z_raw[row_idx]):
                continue
            val = z_raw[row_idx][col_idx]
            if val is None:
                continue
            pct = _display_pct(val)
            values.append(pct)
            tgt = all_targets[row_idx] if row_idx < len(all_targets) else 80
            if pct < tgt:
                critical.append((all_labels[row_idx], pct, tgt))

        if not values or not critical:
            continue

        critical.sort(key=lambda item: item[1])
        worst_pct = critical[0][1]
        worst_gap = min(item[1] - item[2] for item in critical)
        avg = round(sum(values) / len(values), 1)
        rows.append({
            'facility': fac_name,
            'district': _FACILITY_DISTRICT.get(fac_code, ''),
            'facility_type': fac_kind,
            'avg': avg,
            'critical': [(label, pct) for label, pct, _ in critical[:2]],
            'critical_count': len(critical),
            'worst_pct': worst_pct,
            'worst_gap': worst_gap,
        })

    rows.sort(key=lambda row: (row['worst_pct'], row['worst_gap'], -row['critical_count'], row['avg'], row['facility']))
    rows = rows[:5]

    header = html.Tr([
        html.Th('#', className='mnid-attention-th mnid-attention-rank'),
        html.Th('Facility Name', className='mnid-attention-th'),
        html.Th('District', className='mnid-attention-th'),
        html.Th('Facility Type', className='mnid-attention-th'),
        html.Th('Critical Indicator(s)', className='mnid-attention-th'),
        html.Th('Average Performance', className='mnid-attention-th'),
    ])

    if not rows:
        return html.Div(className='mnid-performance-attention-wrap mnid-performance-attention-empty', children=[
            html.Div('FACILITIES REQUIRING ATTENTION', className='mnid-attention-title'),
            html.Div(
                'No facility attention data for this selection.',
                className='mnid-attention-empty-message',
            ),
        ])

    body = []
    for idx, row in enumerate(rows, start=1):
        if row['critical']:
            critical_children = []
            for pos, (label, pct) in enumerate(row['critical']):
                if pos:
                    critical_children.append(html.Br())
                critical_children.append(f'{label} ({pct:.0f}%)')
            critical_cell = html.Div(className='mnid-attention-critical', children=critical_children)
        else:
            critical_cell = html.Span('Monitoring', className='mnid-attention-monitoring')

        avg_color = _cov_color(row['avg'])
        body.append(html.Tr([
            html.Td(str(idx), className='mnid-attention-td mnid-attention-rank'),
            html.Td(row['facility'], className='mnid-attention-td mnid-attention-facility'),
            html.Td(row['district'], className='mnid-attention-td'),
            html.Td(row['facility_type'], className='mnid-attention-td'),
            html.Td(critical_cell, className='mnid-attention-td mnid-attention-critical-cell'),
            html.Td(
                html.Span(f'{row["avg"]:.0f}% (Avg)', style={'color': avg_color}),
                className='mnid-attention-td mnid-attention-avg',
                style={'backgroundColor': '#FFF7ED' if row['avg'] < 65 else ('#FFFBEB' if row['avg'] < 80 else '#F0FDF4')},
            ),
        ]))

    return html.Div(className='mnid-performance-attention-wrap', children=[
        html.Div('FACILITIES REQUIRING ATTENTION', className='mnid-attention-title'),
        html.Table(className='mnid-attention-table', children=[
            html.Thead(header),
            html.Tbody(body),
        ]),
    ])


# MNID heatmap figure builder

def _build_heatmap_fig(stored: dict, view: str, year: str,
                       district: str | None = None,
                       sel_inds: list | None = None) -> go.Figure:
    map_view = view if view in ('by_district', 'district_facs') else 'by_district'
    return _build_geo_heatmap_fig(stored, map_view, year, district, sel_inds)


# # MNID geographic map data for the main heatmap

def _build_geo_heatmap_fig(stored: dict, view: str, year: str,
                           district: str | None = None,
                           sel_inds: list | None = None) -> go.Figure:
    district_avgs = stored.get('district_avgs', {}).get(year, {})
    current_fac   = stored.get('current_fac', '')
    current_dist  = stored.get('current_district', '')
    all_labels    = stored.get('y_labels', [])
    dyn_districts = stored.get('all_districts', [])

    selected_labels = sel_inds if isinstance(sel_inds, list) else ([sel_inds] if sel_inds else [])
    if selected_labels:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in selected_labels]
    else:
        rows_idx = list(range(len(all_labels)))

    by_fac_data = stored.get('by_facility', {}).get(year, {})
    store_fac_x = by_fac_data.get('x', [])
    store_facs  = [f.rstrip('*') for f in store_fac_x]

    def _fac_avg(fac_code):
        fac_z = by_fac_data.get('z', [])
        key = f'{fac_code}*' if fac_code == current_fac else fac_code
        if key not in store_fac_x:
            return None
        ci = store_fac_x.index(key)
        vals = [fac_z[r][ci] for r in rows_idx
                if r < len(fac_z) and ci < len(fac_z[r]) and fac_z[r][ci] is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    selected_dist = district if district not in (None, '', 'All') else None
    focus_dist  = selected_dist or current_dist
    geojson = _load_malawi_district_geojson()
    geo_ref = _build_geo_reference(geojson)
    if not geo_ref:
        fig = go.Figure()
        fig.add_annotation(text='District GeoJSON not available for MNID map',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, height=560)
        return fig

    district_rings = geo_ref.get('district_rings', {})
    district_centroids = geo_ref.get('district_centroids', {})
    y_scale = geo_ref.get('y_scale', 1.0)
    display_districts = sorted(set(dyn_districts) | set(district_rings.keys()) | set(district_avgs.keys()))

    fig = go.Figure()
    shapes = []
    hover_x = []
    hover_y = []
    hover_cd = []
    label_x = []
    label_y = []
    label_text = []

    for dist in display_districts:
        rings = district_rings.get(dist, [])
        if not rings:
            continue
        cov = district_avgs.get(dist)
        fill = _cov_color(cov) if cov is not None else '#E2E8F0'
        is_focus = (view == 'district_facs' and dist == focus_dist) or (view == 'by_district' and dist == selected_dist)
        line_color = '#0F172A' if is_focus else '#FFFFFF'
        line_width = 2.8 if is_focus else 1.4
        for pts in rings:
            path_str = 'M ' + ' L '.join(f'{x:.6f},{y:.6f}' for x, y in pts) + ' Z'
            shapes.append(dict(
                type='path', path=path_str, xref='x', yref='y',
                fillcolor=fill, line=dict(color=line_color, width=line_width), layer='below',
            ))
        cx, cy = district_centroids.get(dist, (None, None))
        if cx is not None and cy is not None:
            hover_x.append(cx)
            hover_y.append(cy)
            hover_cd.append([dist, f'{_display_pct(cov):.1f}%' if cov is not None else 'No data'])
            if view != 'by_facility':
                label_x.append(cx)
                label_y.append(cy)
                label_text.append(f'<b>{dist}</b><br>{_display_pct(cov):.1f}%' if cov is not None else f'<b>{dist}</b><br>No data')

    if shapes:
        fig.update_layout(shapes=shapes)

    if hover_x:
        fig.add_trace(go.Scatter(
            x=hover_x, y=hover_y, mode='markers',
            marker=dict(size=10, color='rgba(0,0,0,0)'),
            customdata=hover_cd,
            hovertemplate='<b>%{customdata[0]}</b><br>Avg coverage: %{customdata[1]}<extra></extra>',
            showlegend=False,
        ))

    if label_x:
        fig.add_trace(go.Scatter(
            x=label_x, y=label_y, mode='text', text=label_text,
            textfont=dict(size=10, color='#FFFFFF', family=FONT),
            hoverinfo='skip', showlegend=False,
        ))

    if view in ('by_facility', 'district_facs'):
        if view == 'by_facility':
            fac_codes = store_facs
        else:
            fac_codes = [f for f in store_facs if _FACILITY_DISTRICT.get(f) == focus_dist]
        facilities_by_district = stored.get('facilities_by_district', {})
        fac_positions = _derive_facility_positions(facilities_by_district, district_centroids)

        fac_x = []
        fac_y = []
        fac_text = []
        fac_size = []
        fac_color = []
        fac_text_pos = []
        for fac in fac_codes:
            pos = fac_positions.get(fac)
            if not pos:
                continue
            x, y = pos
            avg = _fac_avg(fac)
            name = _FACILITY_NAMES.get(fac, fac)
            dist = _FACILITY_DISTRICT.get(fac, '')
            fac_x.append(x)
            fac_y.append(y)
            fac_text.append(f'<b>{name}</b><br>{dist}<br>Avg coverage: {f"{_display_pct(avg):.1f}%" if avg is not None else "No data"}')
            fac_size.append(14 if fac == current_fac else 10)
            fac_color.append(_cov_color(avg) if avg is not None else '#CBD5E1')
            fac_text_pos.append('middle left' if x > 0.55 else 'middle right')

        if fac_x:
            fig.add_trace(go.Scatter(
                x=fac_x, y=fac_y, mode='markers+text',
                text=[_FACILITY_NAMES.get(f, f) for f in fac_codes if fac_positions.get(f)],
                textposition=fac_text_pos,
                textfont=dict(size=9, color=TEXT, family=FONT),
                hovertext=fac_text, hovertemplate='%{hovertext}<extra></extra>',
                marker=dict(size=fac_size, color=fac_color, line=dict(color='#FFFFFF', width=1.2), opacity=0.95),
                showlegend=False,
            ))

    x_range = [-0.02, 1.02]
    y_range = [-0.02, y_scale + 0.02]
    if view == 'district_facs' or (view == 'by_district' and selected_dist):
        zoom_dist = focus_dist if view == 'district_facs' else selected_dist
        focus_points = []
        for pts in district_rings.get(zoom_dist, []):
            focus_points.extend(pts)
        if view == 'district_facs' and 'fac_positions' in locals():
            for fac in [f for f in store_facs if _FACILITY_DISTRICT.get(f) == focus_dist]:
                pos = fac_positions.get(fac)
                if pos:
                    focus_points.append(pos)
        if focus_points:
            xs = [p[0] for p in focus_points]
            ys = [p[1] for p in focus_points]
            pad_x = max((max(xs) - min(xs)) * 0.12, 0.03)
            pad_y = max((max(ys) - min(ys)) * 0.12, 0.03)
            x_range = [max(-0.02, min(xs) - pad_x), min(1.02, max(xs) + pad_x)]
            y_range = [max(-0.02, min(ys) - pad_y), min(y_scale + 0.02, max(ys) + pad_y)]

    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode='markers', showlegend=True,
        marker=dict(
            size=10, color=[0], cmin=0, cmax=100, colorscale=HEATMAP_CS,
            colorbar=dict(
                thickness=14,
                title=dict(text='Coverage %', side='right', font=dict(size=9, color=DIM)),
                tickfont=dict(size=9, color=DIM),
                tickvals=[0, 65, 80, 100],
                ticktext=['0%', '65%', '80%', '100%'],
                len=0.8,
            ),
        ),
        hoverinfo='skip',
    ))

    title = (f'{selected_dist} District Coverage Map' if view == 'by_district' and selected_dist else 'District Coverage Map') if view == 'by_district' else (
        'Facility Coverage Map' if view == 'by_facility' else f'{focus_dist} Facility Coverage Map'
    )
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG, height=560, margin=dict(l=10, r=10, t=34, b=10),
        font=dict(family=FONT, color=TEXT, size=11), hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        hovermode='closest', dragmode='pan',
        xaxis=dict(visible=False, range=x_range, fixedrange=False),
        yaxis=dict(visible=False, range=y_range, fixedrange=False, scaleanchor='x', scaleratio=1),
        transition=dict(duration=450, easing='cubic-in-out'),
        annotations=[dict(
            x=0.01, y=1.03, xref='paper', yref='paper', text=title, showarrow=False, xanchor='left',
            font=dict(size=15, color=TEXT, family=FONT),
        )],
    )
    return fig


# # MNID right panel with Malawi shape and indicator stats

def _build_district_treemap(stored: dict, view: str, year: str,
                             district: str | None = None,
                             sel_inds: list | None = None) -> go.Figure:
    """Treemap of districts/facilities colored by avg indicator coverage - looks like the screenshot."""
    district_avgs = stored.get('district_avgs', {}).get(year, {})
    current_fac   = stored.get('current_fac', '')
    current_dist  = stored.get('current_district', '')
    all_labels    = stored.get('y_labels', [])
    all_targets   = stored.get('y_targets', [])

    if sel_inds:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in sel_inds]
    else:
        rows_idx = list(range(len(all_labels)))

    def _fac_avg(fac_code):
        by_fac = stored.get('by_facility', {}).get(year, {})
        fac_x  = by_fac.get('x', [])
        fac_z  = by_fac.get('z', [])
        key    = f'{fac_code}*' if fac_code == current_fac else fac_code
        if key not in fac_x:
            return None
        ci = fac_x.index(key)
        vals = [fac_z[r][ci] for r in rows_idx
                if r < len(fac_z) and ci < len(fac_z[r]) and fac_z[r][ci] is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    dyn_districts = stored.get('all_districts', [])
    # Derive facility list from store
    by_fac_data  = stored.get('by_facility', {}).get(year, {})
    store_fac_x  = by_fac_data.get('x', [])
    dyn_facs     = [f.rstrip('*') for f in store_fac_x]

    if view in ('by_district', 'monthly', 'yearly'):
        labels  = list(dyn_districts)
        parents = [''] * len(labels)
        values  = [1.0] * len(labels)          # equal weight - coverage drives color
        covs    = [district_avgs.get(d) for d in labels]
        hl_set  = {current_dist} if view in ('monthly', 'yearly') else set(labels)

    elif view == 'by_facility':
        fac_labels  = [f'{_FACILITY_NAMES.get(f, f)}*' if f == current_fac else _FACILITY_NAMES.get(f, f) for f in dyn_facs]
        labels  = list(dyn_districts) + fac_labels
        parents = ([''] * len(dyn_districts) +
                   [_FACILITY_DISTRICT.get(f, '') for f in dyn_facs])
        d_covs  = [district_avgs.get(d) for d in dyn_districts]
        f_covs  = [_fac_avg(f) for f in dyn_facs]
        covs    = d_covs + f_covs
        values  = [1.0] * len(dyn_districts) + [1.0] * len(dyn_facs)
        hl_set  = set(labels)

    elif view == 'district_facs':
        dist_filter = district or current_dist
        facs = [f for f in dyn_facs if _FACILITY_DISTRICT.get(f) == dist_filter]
        labels  = [f'{_FACILITY_NAMES.get(f, f)}*' if f == current_fac else _FACILITY_NAMES.get(f, f) for f in facs]
        parents = [''] * len(labels)
        values  = [1.0] * len(labels)
        covs    = [_fac_avg(f) for f in facs]
        hl_set  = set(labels)

    else:
        labels, parents, values, covs, hl_set = [], [], [], [], set()

    texts  = [f'{_display_pct(c):.0f}%' if c is not None else 'No data' for c in covs]
    colors = [_cov_color(c) if c is not None else '#C8C5BC' for c in covs]
    opacities = [1.0 if lbl in hl_set else 0.45 for lbl in labels]
    final_colors = []
    for col, op in zip(colors, opacities):
        final_colors.append('#D6D3CB' if op < 1.0 else col)

    if not labels:
        fig = go.Figure()
        fig.update_layout(paper_bgcolor=BG, height=200,
                          margin=dict(l=0, r=0, t=0, b=0))
        return fig

    fig = go.Figure(go.Treemap(
        labels=labels,
        parents=parents,
        values=values,
        marker=dict(
            colors=final_colors,
            line=dict(width=2, color='white'),
            cornerradius=4,
        ),
        text=texts,
        customdata=covs,
        hovertemplate='<b>%{label}</b><br>Avg coverage: %{text}<extra></extra>',
        textposition='middle center',
        textfont=dict(size=11, color=TEXT, family=FONT),
        texttemplate='<b>%{label}</b><br>%{text}',
        pathbar=dict(visible=False),
        tiling=dict(squarifyratio=1.5),
    ))

    fig.update_layout(
        paper_bgcolor=BG,
        margin=dict(l=0, r=0, t=4, b=0),
        height=200,
        showlegend=False,
        font=dict(family=FONT),
    )
    return fig


def _build_malawi_panel(stored: dict, view: str, year: str,
                        district: str | None = None,
                        sel_inds: list | None = None) -> list:
    district_avgs    = stored.get('district_avgs', {}).get(year, {})
    current_district = stored.get('current_district', '')
    all_labels       = stored.get('y_labels', [])
    all_targets      = stored.get('y_targets', [])

    # Apply indicator selection filter
    if sel_inds:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in sel_inds]
    else:
        rows_idx = list(range(len(all_labels)))
    y_labels  = [all_labels[i] for i in rows_idx]
    y_targets = [all_targets[i] for i in rows_idx]

    # Which district is highlighted
    if view in ('monthly', 'yearly'):
        highlight = current_district
    elif view == 'district_facs':
        highlight = district or current_district
    elif view == 'by_district' and district not in (None, '', 'All'):
        highlight = district
    else:
        highlight = None

    treemap_fig  = _build_district_treemap(stored, view, year, district, sel_inds)
    malawi_panel = dcc.Graph(
        id='mnid-malawi-treemap',
        figure=treemap_fig,
        config={'displayModeBar': True, 'responsive': True, 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
        style={'marginBottom': '4px', 'height': '170px'},
    )

    # Stats from selected view data
    if view == 'monthly':
        data = stored.get('monthly', {}).get(year, {})
        view_title = 'This facility - monthly'
    elif view == 'by_facility':
        data = stored.get('by_facility', {}).get(year, {})
        view_title = 'All facilities'
    elif view == 'by_district':
        data = stored.get('by_district', {}).get(year, {})
        view_title = f'{district} district' if district not in (None, '', 'All') else 'All districts'
    elif view == 'district_facs':
        dist = district or current_district
        data = stored.get('by_district_facs', {}).get(dist, {}).get(year, {})
        view_title = f'{dist} - district facilities'
    elif view == 'yearly':
        data = stored.get('yearly') or {}
        view_title = 'Year-over-year'
    else:
        data = {}; view_title = ''

    z_raw = data.get('z', [])
    z = [z_raw[i] for i in rows_idx if i < len(z_raw)]
    x = data.get('x', [])

    all_vals    = [v for row in z for v in row if v is not None]
    overall_avg = round(sum(all_vals) / len(all_vals), 1) if all_vals else None

    ind_stats = []
    for ii, (lbl, tgt) in enumerate(zip(y_labels, y_targets)):
        if ii < len(z):
            vals = [z[ii][jj] for jj in range(len(x))
                    if jj < len(z[ii]) and z[ii][jj] is not None]
            if vals:
                avg = round(sum(vals) / len(vals), 1)
                ind_stats.append({'label': lbl, 'target': tgt, 'avg': avg,
                                  'on_target': avg >= tgt})

    on_tgt  = sum(1 for s in ind_stats if s['on_target'])
    ind_rows = []
    for s in sorted(ind_stats, key=lambda x: -x['avg'])[:12]:
        col = _cov_color(s['avg'])
        ind_rows.append(html.Div(style={
            'display': 'flex', 'alignItems': 'center', 'gap': '6px',
            'padding': '3px 0', 'borderBottom': f'0.5px solid {GRID_C}',
        }, children=[
            html.Div(style={'flex': '1', 'minWidth': '0'}, children=[
                html.Div(s['label'], style={
                    'fontSize': '9px', 'color': DIM,
                    'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap',
                }),
                html.Div(style={'height': '2px', 'background': GRID_C,
                                'borderRadius': '1px', 'marginTop': '2px'}, children=[
                    html.Div(style={'width': f'{min(s["avg"], 100):.0f}%', 'height': '100%',
                                    'background': col, 'borderRadius': '1px', 'width': f'{_display_pct(s["avg"]):.0f}%'}),
                ]),
            ]),
            html.Div(style={'textAlign': 'right', 'flexShrink': '0'}, children=[
                html.Span(f'{_display_pct(s["avg"]):.0f}%',
                          style={'fontSize': '10px', 'fontWeight': '600', 'color': col}),
                html.Span(' OK' if s['on_target'] else '',
                          style={'fontSize': '9px', 'color': OK_C}),
            ]),
        ]))

    # Colour legend
    legend_items = [
        (OK_C, '>=80% on target'),
        (WARN_C, '65-79% watch'),
        (DANGER_C, '<65% needs action'),
    ]
    legend = html.Div(style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '5px',
                              'marginTop': '8px', 'marginBottom': '6px'}, children=[
        html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '3px'}, children=[
            html.Div(style={'width': '8px', 'height': '8px', 'borderRadius': '50%',
                            'backgroundColor': c, 'flexShrink': '0'}),
            html.Span(l, style={'fontSize': '9px', 'color': DIM}),
        ])
        for c, l in legend_items
    ])

    # Volume counts for this facility
    counts_for_year = stored.get('counts', {}).get(year, {})
    count_items = []
    for label, val in counts_for_year.items():
        if val > 0:
            count_items.append(html.Div(style={
                'display': 'flex', 'justifyContent': 'space-between',
                'padding': '2px 0', 'borderBottom': f'0.5px solid {GRID_C}',
            }, children=[
                html.Span(label, style={'fontSize': '9px', 'color': DIM}),
                html.Span(f'{val:,}', style={'fontSize': '10px', 'fontWeight': '600',
                                             'color': INFO_C}),
            ]))
    counts_block = html.Div(children=count_items, style={'marginBottom': '8px'}) if count_items else None

    return [
        html.Div('MALAWI COVERAGE', className='mnid-section-lbl'),
        malawi_panel,
        *(([html.Div('ENCOUNTER VOLUMES', className='mnid-section-lbl'), counts_block])
          if counts_block else []),
        legend,
        html.Div(style={'display': 'flex', 'justifyContent': 'space-between',
                        'alignItems': 'baseline', 'marginBottom': '4px'}, children=[
            html.Span(view_title, style={'fontSize': '10px', 'color': MUTED}),
            html.Span(f'{_display_pct(overall_avg):.0f}%' if overall_avg is not None else '-',
                      style={'fontSize': '18px', 'fontWeight': '700',
                             'color': _cov_color(overall_avg)}),
        ]),
        html.Div(f'{on_tgt}/{len(ind_stats)} indicators on target',
                 style={'fontSize': '10px', 'color': MUTED, 'marginBottom': '6px'}),
        html.Div('INDICATOR BREAKDOWN', className='mnid-section-lbl'),
        html.Div(style={'overflowY': 'auto', 'maxHeight': '290px'}, children=ind_rows),
    ]


clientside_callback(
    """
    function(_tick) {
        const sections = [
            '#mnid-summary',
            '#mnid-data-tables',
            '#mnid-trends',
            '#mnid-performance',
            '#mnid-heatmap',
            '#mnid-coverage',
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
    """,
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
    time_grain = time_grain or 'monthly'
    chart_type = chart_type or 'bar'
    ctx = callback_context
    if ctx and ctx.triggered and ctx.triggered[0]['prop_id'] == 'mnid-compare-chart-toggle.n_clicks':
        chart_type = 'line' if chart_type == 'bar' else 'bar'
    store_payload = stored or {}
    tracked = store_payload.get('tracked', [])
    mch_full = _deserialize_store_df(store_payload.get('records'))
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
        return _empty_fig, entity_options, (selected_entities or []), ind_options, selected_ind_ids, chart_type, toggle_class, toggle_text

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
        return _empty_fig, entity_options, [], ind_options, selected_ind_ids, chart_type, toggle_class, toggle_text

    if 'Date' not in mch_full.columns:
        toggle_class = 'mnid-trend-toggle is-bar' if chart_type == 'bar' else 'mnid-trend-toggle is-line'
        toggle_text = 'Bar' if chart_type == 'bar' else 'Line'
        return _empty_fig, entity_options, entities, ind_options, selected_ind_ids, chart_type, toggle_class, toggle_text

    if time_grain == 'quarterly':
        period_code = 'Q'
        period_fmt = lambda p: f"{p.year} Q{p.quarter}"
    elif time_grain == 'yearly':
        period_code = 'Y'
        period_fmt = lambda p: str(p.year)
    else:
        period_code = 'M'
        period_fmt = lambda p: pd.Period(p, 'M').strftime('%b %Y')

    d2 = mch_full.copy()
    d2['_period'] = pd.to_datetime(d2['Date']).dt.to_period(period_code)
    periods = sorted(d2['_period'].dropna().unique())[-12:]

    fig = go.Figure()
    series_idx = 0
    for entity in entities:
        entity_df = get_df(entity).copy()
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
            if not any(y is not None for y in ys):
                continue
            color = _COMPARE_COLORS[series_idx % len(_COMPARE_COLORS)]
            series_idx += 1
            series_name = f'{entity_labels.get(entity, entity)} | {ind["label"]}'
            if chart_type == 'line':
                fig.add_trace(go.Scatter(
                    name=series_name,
                    x=xs,
                    y=ys,
                    mode='lines+markers',
                    line=dict(color=color, width=2.4, shape='spline'),
                    marker=dict(size=6, color=color, line=dict(color='#fff', width=1.0)),
                    hovertemplate=f'<b>{series_name}</b><br>%{{x}}<br>Coverage: %{{y:.1f}}%<extra></extra>',
                    connectgaps=False,
                ))
            else:
                fig.add_trace(go.Bar(
                    name=series_name,
                    x=xs,
                    y=ys,
                    text=texts,
                    textposition='outside',
                    textfont=dict(size=9, color='#E2E8F0'),
                    marker=dict(color=color, opacity=0.88,
                                line=dict(color='rgba(255,255,255,0.25)', width=0.8)),
                    hovertemplate=f'<b>{series_name}</b><br>%{{x}}<br>Coverage: %{{y:.1f}}%<extra></extra>',
                ))

    fig.update_layout(
        height=420,
        barmode='group' if chart_type == 'bar' else None,
        bargap=0.20,
        bargroupgap=0.06,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor='#ffffff',
        plot_bgcolor='#ffffff',
        font=dict(color=TEXT, family=FONT),
        xaxis=dict(showgrid=False, tickfont=dict(size=11, color=TEXT), linecolor=BORDER, title=dict(text='Time', font=dict(size=11, color='#94A3B8'))),
        yaxis=dict(
            title=dict(text='Coverage %', font=dict(size=11, color='#94A3B8')),
            range=[0, 115],
            showgrid=True, gridcolor=GRID_C,
            tickfont=dict(size=10, color=DIM),
        ),
        legend=dict(
            orientation='v', x=1.01, y=1,
            xanchor='left', yanchor='top',
            font=dict(size=10, color=DIM),
            bgcolor='rgba(0,0,0,0)', bordercolor='rgba(0,0,0,0)',
        ),
    )
    toggle_class = 'mnid-trend-toggle is-bar' if chart_type == 'bar' else 'mnid-trend-toggle is-line'
    toggle_text = 'Bar' if chart_type == 'bar' else 'Line'
    return fig, entity_options, entities, ind_options, selected_ind_ids, chart_type, toggle_class, toggle_text


# # MNID main heatmap section layout

def _facilities_requiring_attention(store, year='All years'):
    """Bottom-5 facilities by average MCH coverage - flags needing follow-up."""
    by_fac    = store.get('by_facility', {}).get(year, {})
    fac_x     = by_fac.get('x', [])
    fac_z     = by_fac.get('z', [])
    districts = by_fac.get('districts', [])
    y_targets = store.get('y_targets', [])

    if not fac_x or not fac_z:
        return html.Div()

    rows = []
    for ci, fac in enumerate(fac_x):
        if fac.endswith('*'):   # skip current facility
            continue
        vals = [(fac_z[ri][ci], y_targets[ri] if ri < len(y_targets) else 80)
                for ri in range(len(fac_z))
                if ci < len(fac_z[ri]) and fac_z[ri][ci] is not None]
        if not vals:
            continue
        avg = round(sum(v for v, _ in vals) / len(vals), 1)
        n_critical = sum(1 for v, tgt in vals if v < tgt * 0.85)
        rows.append({
            'fac': fac,
            'fac_name': _FACILITY_NAMES.get(fac, fac),
            'avg': avg,
            'n_critical': n_critical,
            'district': districts[ci] if ci < len(districts) else '',
        })

    if not rows:
        return html.Div()

    rows_sorted = sorted(rows, key=lambda r: r['avg'])[:5]

    hdr_st = {
        'fontSize': '9px', 'fontWeight': '700', 'color': MUTED,
        'padding': '4px 8px', 'borderBottom': f'1.5px solid {BORDER}',
        'textTransform': 'uppercase', 'letterSpacing': '0.06em',
    }
    def _fac_row(r):
        color = _cov_color(r['avg'])
        if r['n_critical'] > 0:
            tag = html.Span(f'{r["n_critical"]} critical', style={
                'background': '#FEF2F2', 'color': DANGER_C,
                'border': '1px solid #FECACA',
                'fontSize': '9px', 'fontWeight': '600',
                'padding': '1px 7px', 'borderRadius': '8px',
            })
        else:
            tag = html.Span('Monitoring', style={
                'background': '#FFFBEB', 'color': '#92400E',
                'border': '1px solid #FDE68A',
                'fontSize': '9px', 'fontWeight': '600',
                'padding': '1px 7px', 'borderRadius': '8px',
            })
        return html.Tr(children=[
            html.Td(r['fac_name'], style={
                'fontSize': '11px', 'fontWeight': '600', 'padding': '7px 8px', 'color': TEXT,
            }),
            html.Td(r['district'], style={'fontSize': '10px', 'color': MUTED, 'padding': '7px 8px'}),
            html.Td(f'{_display_pct(r["avg"]):.0f}%', style={
                'fontSize': '13px', 'fontWeight': '700', 'color': color, 'padding': '7px 8px',
                'textAlign': 'center',
            }),
            html.Td(tag, style={'padding': '7px 8px', 'textAlign': 'left'}),
        ])

    return html.Div(className='mnid-card', style={'marginBottom': '12px'}, children=[
        html.Div('FACILITIES REQUIRING ATTENTION', className='mnid-section-lbl'),
        html.P(
            'Bottom 5 facilities by average coverage across all tracked MCH indicators.',
            style={'fontSize': '10px', 'color': MUTED, 'marginBottom': '8px'},
        ),
        html.Table(className='mnid-priority-tbl', children=[
            html.Thead(html.Tr([
                html.Th('Facility', style=hdr_st),
                html.Th('District', style=hdr_st),
                html.Th('Avg Cov.', style=hdr_st),
                html.Th('Indicators', style=hdr_st),
            ])),
            html.Tbody([_fac_row(r) for r in rows_sorted]),
        ]),
    ])


def _coverage_heatmap_section(indicators: list, facility_code: str,
                              mch_full: pd.DataFrame) -> html.Div:
    """Multi-view indicator heatmap with Malawi district panel and live filters."""
    tracked = [i for i in indicators if i.get('status') == 'tracked']
    store   = _compute_heatmap_store(mch_full, tracked, facility_code)

    district_gauges = _build_district_gauge_row(store)

    initial_fig   = _build_heatmap_fig(store, 'by_district', 'All years')
    initial_panel = _build_malawi_panel(store, 'by_district', 'All years')

    dyn_districts = store.get('all_districts', [])
    cur_dist   = store.get('current_district', dyn_districts[0] if dyn_districts else '')
    all_labels = store.get('y_labels', [])
    years = ['All years']
    if len(mch_full) and 'Date' in mch_full.columns:
        years.extend(str(y) for y in sorted(mch_full['Date'].dt.year.dropna().astype(int).unique().tolist()))

    year_opts     = [{'label': y, 'value': y} for y in years]
    district_opts = [{'label': 'All districts', 'value': 'All'}] + [{'label': d, 'value': d} for d in dyn_districts]
    ind_opts      = [{'label': lbl, 'value': lbl} for lbl in all_labels]
    default_perf_inds = all_labels[:8] if len(all_labels) >= 8 else all_labels

    _dd_style = {'fontSize': '12px', 'minWidth': '0'}
    _lbl_style = {'fontSize': '10px', 'color': MUTED, 'fontWeight': '600',
                  'marginBottom': '3px'}

    performance_card = html.Div(className='mnid-card mnid-performance-block',
                    style={'marginBottom': '12px'}, children=[
        dcc.Store(id='mnid-heatmap-store', data=store),
        html.Div('FACILITY PERFORMANCE', className='mnid-section-lbl'),
        html.Div(style={'fontSize': '11px', 'color': DIM, 'marginBottom': '10px'},
                 children='District comparison heatmap for key performance indicators.'),
        html.Div(className='mnid-performance-shell', children=[
            html.Div(id='mnid-performance-aggregate', className='mnid-performance-aggregate',
                     children=_build_district_gauge_row(store, 'All years')),
            html.Div(className='mnid-performance-table-card', children=[
                html.Div(className='mnid-performance-filter', style={'marginBottom': '10px'}, children=[
                    html.Div('Indicators', style=_lbl_style),
                    dcc.Dropdown(
                        id='mnid-performance-indicators',
                        options=ind_opts,
                        value=default_perf_inds,
                        multi=True,
                        placeholder='Select indicators...',
                        style=_dd_style,
                    ),
                ]),
                html.Div(
                    id='mnid-performance-heatmap-table',
                    className='mnid-performance-heatmap-graph',
                    children=_build_facility_performance_heatmap_fig(store, 'All years', 'All', default_perf_inds, 'All'),
                ),
                html.Div(className='mnid-performance-key', children=[
                    html.Div('Performance Color Scale', className='mnid-performance-key-title'),
                    html.Div(className='mnid-performance-key-row', children=[html.Span('Excellent (>90%)'), html.Div(className='mnid-performance-swatch excellent')]),
                    html.Div(className='mnid-performance-key-row', children=[html.Span('Moderate (60-80%)'), html.Div(className='mnid-performance-swatch moderate')]),
                    html.Div(className='mnid-performance-key-row', children=[html.Span('Poor (<50%)'), html.Div(className='mnid-performance-swatch poor')]),
                ]),
                html.Div(
                    id='mnid-performance-attention',
                    className='mnid-performance-attention',
                    children=_build_performance_attention_table(store, 'All years', 'All', 'All', default_perf_inds),
                ),
            ]),
        ]),
    ])

    heatmap_card = html.Div(id='mnid-heatmap-inner', className='mnid-card',
                    style={'marginBottom': '12px'}, children=[
        html.Div('MAP COVERAGE VIEW', className='mnid-section-lbl'),

        html.Div(className='mnid-map-controls', children=[
            html.Div(className='mnid-map-scope', children=[
                html.Div('Scope', style=_lbl_style),
                dmc.SegmentedControl(
                    id='mnid-heatmap-view',
                    value='by_district',
                    data=[
                        {'label': 'Districts', 'value': 'by_district'},
                        {'label': 'Facilities', 'value': 'district_facs'},
                    ],
                    size='sm',
                    radius='xl',
                    color='green',
                    fullWidth=True,
                ),
            ]),
            html.Div(className='mnid-map-filter-grid', children=[
                html.Div(id='mnid-heatmap-district-wrap', style={'display': 'none'}, children=[
                    html.Div('District Focus', style=_lbl_style),
                    dcc.Dropdown(
                        id='mnid-heatmap-district',
                        options=district_opts,
                        value='All',
                        clearable=False,
                        style=_dd_style,
                    ),
                ]),
                html.Div(children=[
                    html.Div('Indicators', style=_lbl_style),
                    dcc.Dropdown(
                        id='mnid-heatmap-indicators',
                        options=ind_opts,
                        value=all_labels[0] if all_labels else None,
                        clearable=False,
                        placeholder='Select indicator...',
                        style=_dd_style,
                    ),
                ]),
            ]),
        ]),

        html.Div(className='mnid-heatmap-grid', children=[
            dcc.Graph(
                id='mnid-heatmap-graph',
                className='mnid-heatmap-map',
                animate=True,
                config={'displayModeBar': True,
                        'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                        'scrollZoom': True,
                        'responsive': True,
                        'doubleClick': 'reset'}
                , figure=initial_fig,
                style={'height': '560px', 'width': '100%', 'minWidth': '0'},
                clear_on_unhover=False,
            ),
            html.Div(
                id='mnid-heatmap-right',
                className='mnid-heatmap-panel',
                children=initial_panel,
            ),
        ]),

        html.P(
            'Click the scope toggle to switch between district coverage and facility markers. Choose a district when viewing facilities to keep the map readable.',
            style={'fontSize': '10px', 'color': MUTED, 'marginTop': '8px', 'lineHeight': '1.5'},
        ),
    ])

    return performance_card, heatmap_card

# indicator cards

def _ind_card(ind: dict, df: pd.DataFrame) -> html.Div:
    if ind.get('status') == 'awaiting_baseline':
        return html.Div(className='mnid-ind-card awaiting', children=[
            html.Div(ind['label'], className='mnid-ind-label'),
            html.Div([
                html.Span('-', className='mnid-ind-pct info'),
                html.Span('Awaiting baseline', className='mnid-tag mnid-tag-amber'),
            ], className='mnid-ind-top'),
            html.Div(f'Target {ind["target"]}%', className='mnid-ind-sub'),
        ])

    num, den, pct = _cov(df, ind['numerator_filters'], ind['denominator_filters'])
    target = ind['target']
    cls = _css(pct, target)

    if pct >= target:
        badge = html.Span('On target',    className='mnid-tag mnid-tag-green')
    elif pct >= target * 0.85:
        badge = html.Span('Performing',  className='mnid-tag mnid-tag-blue')
    else:
        badge = html.Span('Needs review', className='mnid-tag mnid-tag-red')

    return html.Div(className=f'mnid-ind-card {cls}', children=[
        html.Div(ind['label'], className='mnid-ind-label'),
        html.Div([
            html.Span(f'{_display_pct(pct):.0f}%', className=f'mnid-ind-pct {cls}'),
            badge,
        ], className='mnid-ind-top'),
        html.Div(f'{num} / {den}  -  Target {target}%', className='mnid-ind-sub'),
    ])


# # MNID phase gauge donuts

def _phase_gauge_fig(avg_pct: float, color: str) -> go.Figure:
    """Mini donut gauge for a single care phase."""
    rest = max(0.0, 100.0 - avg_pct)
    fig = go.Figure(go.Pie(
        values=[avg_pct, rest],
        hole=0.72,
        marker=dict(colors=[color, GRID_C], line=dict(color='#fff', width=0)),
        textinfo='none',
        hoverinfo='skip',
        sort=False,
        direction='clockwise',
        rotation=90,
    ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        margin=dict(l=4, r=4, t=4, b=4),
        height=100,
        showlegend=False,
        annotations=[dict(
            text=f'<b>{_display_pct(avg_pct):.0f}%</b>',
            x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False,
            font=dict(size=20, color=color, family=FONT),
        )],
    )
    return fig


def _phase_gauge_row(by_cat: dict, df: pd.DataFrame) -> html.Div:
    """Row of 4 mini donut gauges - one per care phase."""
    phases = [
        ('ANC',     'Antenatal Care',    CAT_PALETTES['ANC'][0],     'anc'),
        ('Labour',  'Labour & Delivery', CAT_PALETTES['Labour'][0],  'labour'),
        ('Newborn', 'Newborn Care',       CAT_PALETTES['Newborn'][0], 'newborn'),
        ('PNC',     'Postnatal Care',    CAT_PALETTES['PNC'][0],     'pnc'),
    ]
    cards = []
    for cat_key, cat_label, cat_color, css_cls in phases:
        inds = [i for i in by_cat.get(cat_key, []) if i.get('status') == 'tracked']
        if not inds:
            continue
        computed = [_cov(df, i['numerator_filters'], i['denominator_filters'])
                    for i in inds]
        avg_pct = round(sum(c[2] for c in computed) / len(computed), 1) if computed else 0.0
        on_tgt  = sum(1 for c, i in zip(computed, inds) if c[2] >= i['target'])
        color   = _cov_color(avg_pct)

        fig = _phase_gauge_fig(avg_pct, color)
        cards.append(html.Div(className=f'mnid-phase-gauge {css_cls}', children=[
            html.Div(cat_label, className='mnid-phase-gauge-title'),
            dcc.Graph(figure=fig, config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                      style={'height': '100px'}),
            html.Div(className='mnid-phase-gauge-on', children=[
                html.B(f'{on_tgt}/{len(inds)}'), ' on target',
            ]),
        ]))
    return html.Div(className='mnid-gauge-row', children=cards)


# # MNID key clinical outcomes

def _clinical_donuts_section(df: pd.DataFrame) -> html.Div:
    """Always-visible donut row for key clinical outcomes."""
    donut_specs = [
        ('Place of delivery', 'Place of Delivery', {
            'This facility': OK_C, 'this facility': OK_C,
            'Referral facility': WARN_C, 'Home': DANGER_C,
        }),
        ('Outcome of the delivery', 'Birth Outcome', {
            'Live births': OK_C,
            'Fresh stillbirth': DANGER_C,
            'Macerated stillbirth': '#92400E',
        }),
        ('Breast feeding', 'Breastfeeding Mode', {
            'Exclusive': OK_C, 'Mixed': WARN_C, 'Not breastfeeding': DANGER_C,
        }),
        ('Thermal status on admission', 'Newborn Thermal Status', {
            'Not hypothermic': OK_C,
            'Mild hypothermia': WARN_C,
            'Moderate hypothermia': DANGER_C,
        }),
    ]
    cards = []
    for concept, title, color_map in donut_specs:
        vc  = _value_counts(df, concept)
        fig = _donut(vc, title, color_map=color_map)
        if fig:
            fig.update_layout(height=200, margin=dict(l=4, r=4, t=32, b=28))
            cards.append(html.Div(className='mnid-chart-card', children=[
                dcc.Graph(figure=fig, config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                          style={'height': '200px'}),
            ]))

    if not cards:
        return html.Div()

    return html.Div([
        html.Div('KEY CLINICAL OUTCOMES', className='mnid-section-lbl'),
        html.Div(className='mnid-donut-grid', children=cards),
    ])


# # MNID coverage phase bar chart

def _coverage_phase_fig(title: str, indicators: list, df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart: one bar per indicator coloured by status vs target."""
    rows = []
    for ind in indicators:
        if ind.get('status') == 'awaiting_baseline':
            rows.append({'label': ind['label'][:36], 'pct': None,
                         'target': ind['target'], 'cls': 'await',
                         'sub': 'Awaiting baseline'})
        else:
            num, den, pct = _cov(df, ind['numerator_filters'], ind['denominator_filters'])
            cls = _css(pct, ind['target'])
            rows.append({'label': ind['label'][:36], 'pct': pct,
                         'target': ind['target'], 'cls': cls,
                         'sub': f'{num}/{den}'})

    if not rows:
        return go.Figure()

    # Reversed so first indicator is at the top
    rows = list(reversed(rows))
    labels  = [r['label']  for r in rows]
    values  = [r['pct'] if r['pct'] is not None else 0 for r in rows]
    targets = [r['target'] for r in rows]
    colors  = [{'ok': OK_C, 'warn': WARN_C, 'danger': DANGER_C}.get(r['cls'], MUTED)
               for r in rows]
    text_vals = [f"{r['pct']:.0f}%" if r['pct'] is not None else 'No data' for r in rows]

    height = max(len(rows) * 38 + 70, 180)

    fig = go.Figure()

    # Bars
    fig.add_trace(go.Bar(
        x=values, y=labels,
        orientation='h',
        marker=dict(color=colors, opacity=0.88,
                    line=dict(color='rgba(0,0,0,0)')),
        text=text_vals,
        textposition='outside',
        textfont=dict(size=10, color=TEXT, family=FONT),
        cliponaxis=False,
        hovertemplate='<b>%{y}</b><br>Coverage: %{x:.1f}%<extra></extra>',
        showlegend=False,
    ))

    # Target markers as a scatter overlay
    fig.add_trace(go.Scatter(
        x=targets, y=labels,
        mode='markers',
        marker=dict(symbol='line-ew', size=14, color='#64748B',
                    line=dict(color='#64748B', width=2)),
        name='Target',
        hovertemplate='Target: %{x:.0f}%<extra></extra>',
    ))

    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        height=height,
        margin=dict(l=8, r=56, t=8, b=8),
        xaxis=dict(range=[0, 115], showgrid=True, gridcolor=GRID_C,
                   zeroline=False, showline=False,
                   ticksuffix='%', tickfont=dict(size=9, color=MUTED)),
        yaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=DIM), automargin=True),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        legend=dict(orientation='h', x=0, y=-0.06, xanchor='left',
                    font=dict(size=9, color=DIM)),
        bargap=0.28,
    )
    return fig


def _no_data_card(message: str = 'No data available for this period.') -> html.Div:
    """Inline empty-state card for individual chart sections."""
    return html.Div(className='mnid-chart-card', style={'gridColumn': '1 / -1'}, children=[
        html.Div(style={
            'display': 'flex', 'flexDirection': 'column',
            'alignItems': 'center', 'justifyContent': 'center',
            'padding': '40px 24px', 'gap': '10px',
        }, children=[
            html.Div('-', style={
                'fontSize': '32px', 'color': MUTED, 'lineHeight': '1',
            }),
            html.Div(message, style={
                'fontSize': '13px', 'color': DIM, 'fontFamily': FONT,
                'textAlign': 'center',
            }),
        ]),
    ])


def _coverage_charts_section(by_cat: dict, df: pd.DataFrame, categories: list | None = None) -> html.Div:
    """2-column grid of per-phase coverage bar charts (replaces accordion cards)."""
    phase_map = {
        'ANC': 'Antenatal Care (ANC)',
        'Labour': 'Labour & Delivery',
        'Newborn': 'Newborn Care',
        'PNC': 'Postnatal Care (PNC)',
    }
    phases = [(cat, phase_map.get(cat, cat)) for cat in _resolve_category_order(
        [{'category': k} for k in by_cat.keys()], categories
    )]
    cards = []
    for cat_key, cat_title in phases:
        inds = by_cat.get(cat_key, [])
        if not inds:
            continue
        tracked  = [i for i in inds if i.get('status') == 'tracked']
        awaiting = [i for i in inds if i.get('status') == 'awaiting_baseline']
        computed = [_cov(df, i['numerator_filters'], i['denominator_filters'])
                    for i in tracked]
        avg_pct  = round(sum(c[2] for c in computed) / len(computed), 0) if computed else None

        pills = [html.Span(f'{len(tracked)} available', className='mnid-pill mnid-pill-green')]
        if awaiting:
            pills.append(html.Span(f'{len(awaiting)} awaiting', className='mnid-pill mnid-pill-amber'))
        if avg_pct is not None:
            pc = 'mnid-pill-green' if avg_pct >= 80 else ('mnid-pill-amber' if avg_pct >= 65 else 'mnid-pill-red')
            pills.append(html.Span(f'Avg {_display_pct(avg_pct):.0f}%', className=f'mnid-pill {pc}'))

        fig = _coverage_phase_fig(cat_title, inds, df)
        h   = max(len(inds) * 38 + 70, 180)

        cards.append(html.Div(className='mnid-chart-card', children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-between',
                            'alignItems': 'center', 'marginBottom': '4px'}, children=[
                html.Div(cat_title,
                         style={'fontSize': '12px', 'fontWeight': '600', 'color': TEXT}),
                html.Div(className='mnid-pills', children=pills),
            ]),
            dcc.Graph(figure=fig, config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                      style={'height': f'{h}px'}),
            html.P('|= target', style={'fontSize': '9px', 'color': MUTED,
                                        'margin': '2px 0 0', 'textAlign': 'right'}),
        ]))

    if not cards:
        return html.Div(className='mnid-chart-grid',
                        children=[_no_data_card('No indicators configured for this facility.')])
    return html.Div(className='mnid-chart-grid', children=cards)


# accordion helpers (kept for analysis sections)

def _acc_section(sec_id, title, indicators, df, default_open=False):
    tracked  = [i for i in indicators if i.get('status') == 'tracked']
    awaiting = [i for i in indicators if i.get('status') == 'awaiting_baseline']
    computed = [_cov(df, i['numerator_filters'], i['denominator_filters'])
                for i in tracked]
    avg_pct  = round(sum(c[2] for c in computed) / len(computed), 0) if computed else None

    pills = [html.Span(f'{len(tracked)} available', className='mnid-pill mnid-pill-green')]
    if awaiting:
        pills.append(html.Span(f'{len(awaiting)} awaiting',
                               className='mnid-pill mnid-pill-amber'))
    if avg_pct is not None:
        pc = 'mnid-pill-green' if avg_pct >= 80 else ('mnid-pill-amber' if avg_pct >= 65
                                                        else 'mnid-pill-red')
        pills.append(html.Span(f'Avg {_display_pct(avg_pct):.0f}%', className=f'mnid-pill {pc}'))

    return dmc.AccordionItem(value=sec_id, children=[
        dmc.AccordionControl(html.Div(style={
            'display':'flex','alignItems':'center',
            'justifyContent':'space-between','width':'100%','gap':'12px',
        }, children=[
            html.Span(title, style={'fontSize':'13px','fontWeight':'500','color':TEXT}),
            html.Div(className='mnid-pills', children=pills),
        ])),
        dmc.AccordionPanel(
            html.Div(className='mnid-ind-grid',
                     children=[_ind_card(i, df) for i in indicators]),
            pt='sm', pb='md',
        ),
    ])


def _chart_acc_section(sec_id, title, charts):
    """Accordion panel containing chart cards in a responsive 2-col grid."""
    return dmc.AccordionItem(value=sec_id, children=[
        dmc.AccordionControl(
            html.Span(title, style={'fontSize':'13px','fontWeight':'500','color':TEXT})
        ),
        dmc.AccordionPanel(
            html.Div(className='mnid-chart-grid', children=charts),
            pt='sm', pb='md',
        ),
    ])


# themed analysis charts 

def _anc_charts(df):
    monthly = _monthly_visits(df, 'ANC VISIT')
    charts = []

    fig = _line(monthly, 'ANC Visits Over Time', color=_TREND_ACCENT['ANC'], y_label='Unique Clients')
    if fig: charts.append(_chart_card('', fig))

    for concept, title in [
        ('Anemia screening',            'Anaemia Screening'),
        ('Infection screening',         'Infection Screening'),
        ('High blood pressure screening','Blood Pressure Screening'),
    ]:
        vc = _value_counts(df, concept)
        fig = _donut(vc, title, color_map={
            'Screened': '#2563EB', 'Not screened': '#94A3B8',
        })
        if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'POCUS completed')
    fig = _donut(vc, 'POCUS Completed', color_map={'Yes': '#0F766E', 'No': '#94A3B8'})
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'HIV Test')
    fig = _donut(vc, 'HIV Testing Status', color_map={
        'Non-reactive': '#2563EB', 'Reactive': '#DB2777',
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Number of tetanus doses', col='Value')
    fig = _hbar(vc, 'Tetanus Dose Distribution')
    if fig: charts.append(_chart_card('', fig))

    return charts


def _labour_charts(df):
    charts = []

    cascade = _pph_cascade(df)
    if cascade:
        charts.append(cascade)

    monthly = _monthly_visits(df, 'LABOUR AND DELIVERY')
    fig = _line(monthly, 'Labour & Delivery Visits', color=_TREND_ACCENT['Labour'], y_label='Clients')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Place of delivery')
    fig = _donut(vc, 'Place of Delivery', color_map={
        'This facility': '#2563EB', 'this facility': '#2563EB',
        'Referral facility': '#0F766E', 'Home': '#C2410C', 'In transit': '#64748B',
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Mode of delivery')
    fig = _donut(vc, 'Mode of Delivery')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Obstetric complications')
    fig = _hbar(vc, 'Obstetric Complications')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Outcome of the delivery')
    fig = _donut(vc, 'Birth Outcome', color_map={
        'Live births': '#0F766E',
        'Fresh stillbirth': '#DB2777',
        'Macerated stillbirth': '#7C3AED',
    })
    if fig: charts.append(_chart_card('', fig))

    for concept, label in [
        ('Antenatal corticosteroids given', 'Antenatal Corticosteroids'),
        ('Prophylactic azithromycin given', 'Prophylactic Azithromycin'),
        ('PPH treatment bundle',            'PPH Treatment Bundle'),
        ('Digital intrapartum monitoring',  'Digital Monitoring'),
    ]:
        vc = _value_counts(df, concept)
        fig = _donut(vc, label, color_map={
            'Yes': '#2563EB', 'Used': '#2563EB', 'Completed': '#2563EB',
            'Partial': '#C2410C',
            'No': '#94A3B8', 'Not used': '#94A3B8',
            'Not required': '#CBD5E1', 'Not eligible': '#CBD5E1',
        })
        if fig: charts.append(_chart_card('', fig))

    return charts


def _pnc_charts(df):
    charts = []
    monthly = _monthly_visits(df, 'POSTNATAL CARE')
    fig = _line(monthly, 'PNC Visits Over Time', color=_TREND_ACCENT['PNC'], y_label='Clients')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Postnatal check period')
    fig = _hbar(vc, 'PNC Visit Timing')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Breast feeding')
    fig = _donut(vc, 'Breastfeeding Mode', color_map={
        'Exclusive': '#2563EB', 'exclusive breastfeeding': '#2563EB',
        'Mixed': '#0F766E', 'Not breastfeeding': '#7C3AED',
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Status of the mother')
    fig = _donut(vc, 'Mother Final Status', color_map={
        'Stable': '#2563EB', 'Referred': '#C2410C', 'Death': '#DB2777',
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Status of baby')
    fig = _donut(vc, 'Baby Final Status', color_map={
        'Stable': '#2563EB', 'Referred': '#C2410C', 'Died': '#DB2777',
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Postnatal complications')
    fig = _hbar(vc, 'Postnatal Complications')
    if fig: charts.append(_chart_card('', fig))

    return charts


def _newborn_charts(df):
    monthly = _monthly_visits(df, 'NEONATAL CARE')
    fig = _line(monthly, 'Neonatal Care Admissions', color=_TREND_ACCENT['Newborn'], y_label='Babies')
    admission_card = _chart_card('', fig) if fig else None

    thermal_num, thermal_den, thermal_pct = _concept_rate(df, 'Thermal status on admission', ['Not hypothermic'])
    resus_num, resus_den, resus_pct = _concept_rate(df, 'Neonatal resuscitation provided', ['Yes', 'Stimulation only', 'Bag and mask'])
    kmc_num, kmc_den, kmc_pct = _concept_rate(df, 'iKMC initiated', ['Yes'])
    support_num, support_den, support_pct = _concept_rate(df, 'CPAP support', ['Bubble CPAP', 'Nasal oxygen'])

    summary_cards = [
        _newborn_summary_card('Thermal Stability', thermal_num, thermal_den, thermal_pct, '#0F766E',
                              'Babies arriving normothermic'),
        _newborn_summary_card('Resuscitation Response', resus_num, resus_den, resus_pct, '#2563EB',
                              'Babies receiving any resuscitation action'),
        _newborn_summary_card('iKMC Initiation', kmc_num, kmc_den, kmc_pct, '#7C3AED',
                              'Eligible babies initiated on KMC'),
        _newborn_summary_card('Respiratory Support', support_num, support_den, support_pct, '#0891B2',
                              'Bubble CPAP or nasal oxygen recorded'),
    ]
    overview_card = html.Div(className='mnid-chart-card', children=[
        html.Div(className='mnid-newborn-metric-grid', children=summary_cards)
    ])

    run_specs = [
        ('Thermal status on admission', ['Not hypothermic'], 'Thermal Stability', 85, '#0F766E'),
        ('Neonatal resuscitation provided', ['Yes', 'Stimulation only', 'Bag and mask'], 'Resuscitation Response', 80, '#2563EB'),
        ('iKMC initiated', ['Yes'], 'iKMC Initiation', 75, '#7C3AED'),
        ('Phototherapy given', ['Yes'], 'Phototherapy Use', 70, '#C2410C'),
        ('Parenteral antibiotics given', ['Yes'], 'Antibiotics Given', 85, '#DB2777'),
        ('CPAP support', ['Bubble CPAP'], 'Bubble CPAP Use', 60, '#0891B2'),
    ]
    run_cards = {}
    for concept, values, title, target, color in run_specs:
        run_fig = _monthly_concept_rate(df, concept, positive_values=values, title=title, target=target, color=color)
        if run_fig:
            run_cards[title] = html.Div(className='mnid-chart-card', children=[
                dcc.Graph(
                    figure=run_fig,
                    config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                    style={'height': '210px'},
                ),
            ])

    mix_fig = _monthly_concept_mix_fig(
        df,
        'Thermal status on admission',
        [
            ('Not hypothermic', ['Not hypothermic'], '#2563EB'),
            ('Mild hypothermia', ['Mild hypothermia'], '#0F766E'),
            ('Moderate/Severe', ['Moderate hypothermia', 'Severe hypothermia'], '#DB2777'),
        ],
        'Thermal Status Mix Over Time',
    )
    thermal_mix_card = _chart_card('', mix_fig) if mix_fig else None

    resp_mix_fig = _monthly_concept_mix_fig(
        df,
        'CPAP support',
        [
            ('Bubble CPAP', ['Bubble CPAP'], '#7C3AED'),
            ('Nasal oxygen', ['Nasal oxygen'], '#0891B2'),
            ('No advanced support', ['None', 'No'], '#CBD5E1'),
        ],
        'Respiratory Support Mix Over Time',
    )
    respiratory_mix_card = _chart_card('', resp_mix_fig) if resp_mix_fig else None

    vc = _value_counts(df, 'Thermal status on admission')
    fig = _donut(vc, 'Thermal Status on Admission', color_map={
        'Not hypothermic': '#2563EB',
        'Mild hypothermia': '#0F766E',
        'Moderate hypothermia': '#C2410C',
        'Severe hypothermia': '#DB2777',
    })
    thermal_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'Neonatal resuscitation provided')
    fig = _donut(vc, 'Neonatal Resuscitation', color_map={
        'Yes': '#2563EB', 'Stimulation only': '#0F766E',
        'Bag and mask': '#7C3AED', 'No': '#94A3B8', 'Not required': '#CBD5E1',
    })
    resuscitation_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'iKMC initiated')
    fig = _donut(vc, 'iKMC Initiated', color_map={
        'Yes': '#2563EB', 'No': '#94A3B8', 'Not eligible': '#CBD5E1',
    })
    kmc_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'CPAP support')
    fig = _donut(vc, 'CPAP Support Type', color_map={
        'Bubble CPAP': '#2563EB', 'Nasal oxygen': '#0F766E', 'None': '#94A3B8',
    })
    cpap_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'Phototherapy given')
    fig = _donut(vc, 'Phototherapy Given', color_map={
        'Yes': '#2563EB', 'No': '#94A3B8',
    })
    phototherapy_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'Parenteral antibiotics given')
    fig = _donut(vc, 'Parenteral Antibiotics', color_map={
        'Yes': '#2563EB', 'No': '#94A3B8',
    })
    antibiotics_donut = _chart_card('', fig) if fig else None

    vc = _value_counts(df, 'Newborn baby complications')
    fig = _hbar(vc, 'Newborn Complications')
    complications_bar = _chart_card('', fig) if fig else None

    birthweight_vc, birthweight_concept = _first_available_value_counts(
        df,
        ['Birthweight category', 'Birth weight category', 'Birthweight', 'Birth weight'],
        col='obs_value_coded',
    )
    birthweight_chart = None
    if len(birthweight_vc):
        birthweight_fig = _hbar(birthweight_vc, 'Birthweight Distribution', color='#7C3AED')
        if birthweight_fig:
            birthweight_chart = _chart_card('', birthweight_fig)

    mortality_vc, mortality_concept = _first_available_value_counts(
        df,
        ['Status of baby', 'Baby Final Status', 'Outcome of the delivery'],
        col='obs_value_coded',
    )
    mortality_chart = None
    if len(mortality_vc):
        mortality_fig = _donut(mortality_vc, 'Outcome Status', color_map={
            'Stable': '#2563EB', 'Alive': '#2563EB', 'Live births': '#2563EB',
            'Referred': '#C2410C', 'Died': '#DB2777', 'Death': '#DB2777',
            'Fresh stillbirth': '#DB2777', 'Macerated stillbirth': '#7C3AED',
        })
        if mortality_fig:
            mortality_chart = _chart_card('', mortality_fig)

    diagnosis_chart = complications_bar
    quality_cards = [card for card in [phototherapy_donut, antibiotics_donut, thermal_donut] if card is not None]

    tab_specs = [
        ('Admissions', 'Admissions volume and core neonatal service activity.', [overview_card, admission_card]),
        ('Mortality', 'Outcome trends and mortality-related newborn status views.', [mortality_chart]),
        ('Birthweight', 'Birthweight-related distribution views for neonatal review.', [birthweight_chart]),
        ('Thermal Care', 'Thermal stability monitoring and thermal status composition.', [run_cards.get('Thermal Stability'), thermal_mix_card, thermal_donut]),
        ('Respiratory Support', 'Respiratory support and resuscitation monitoring.', [run_cards.get('Resuscitation Response'), run_cards.get('Bubble CPAP Use'), respiratory_mix_card, resuscitation_donut, cpap_donut]),
        ('KMC', 'KMC uptake and related newborn care monitoring.', [run_cards.get('iKMC Initiation'), kmc_donut]),
        ('Infections', 'Infection-related treatment and complication monitoring.', [run_cards.get('Antibiotics Given'), antibiotics_donut, diagnosis_chart]),
        ('Quality of Care', 'Selected intervention and support measures used to review care delivery.', quality_cards),
    ]
    tabs = []
    for label, desc, cards in tab_specs:
        usable_cards = [card for card in cards if card is not None]
        if usable_cards:
            tabs.append((label, desc, usable_cards))

    return [html.Div(className='mnid-chart-card mnid-newborn-workspace', style={'gridColumn': '1 / -1'}, children=[
        html.Div('NEONATAL CLINICAL MODULES', className='mnid-card-title'),
        html.Div('Select a module to view the relevant neonatal charts and indicators.',
                 className='mnid-newborn-section-subtitle', style={'marginBottom': '12px'}),
        dcc.Tabs(
            value=(tabs[0][0] if tabs else 'Admissions'),
            className='mnid-newborn-tabs',
            children=[
                dcc.Tab(
                    label=label,
                    value=label,
                    className='mnid-newborn-tab',
                    selected_className='mnid-newborn-tab--selected',
                    children=_newborn_tab_content(desc, cards),
                )
                for label, desc, cards in tabs
            ],
        ),
    ])]


# system readiness

def _stat_row(label, num, den, pct, tgt=None):
    cls = _css(pct, tgt) if tgt else 'info'
    status_map = {'ok': 'On target', 'warn': 'Watch', 'danger': 'Needs action', 'info': 'Monitor'}
    return html.Div(className=f'mnid-stat-row {cls}', children=[
        html.Span(label, className='mnid-stat-lbl'),
        html.Div(style={'display':'flex','gap':'8px','alignItems':'center', 'flexWrap': 'wrap', 'justifyContent': 'flex-end'}, children=[
            html.Span(f'{num}/{den}', className=f'mnid-stat-meta {cls}'),
            html.Span(f'{_display_pct(pct):.0f}%', className=f'mnid-stat-val {cls}'),
            html.Span(status_map.get(cls, 'Monitor'), className=f'mnid-stat-tag {cls}'),
        ]),
    ])


def _system_readiness(df, supply_inds, wf_inds, dq_inds):
    if not (supply_inds or wf_inds or dq_inds):
        return html.Div()

    def _rows(inds, tgt_key='target_pct'):
        rows = []
        for ind in inds:
            num, den, pct = _cov(df, ind['numerator_filters'], ind['denominator_filters'])
            rows.append(_stat_row(ind['label'], num, den, pct, ind.get(tgt_key)))
        return rows

    return html.Div([
        html.Div('SYSTEM READINESS', className='mnid-section-lbl'),
        html.Div(className='mnid-grid3', children=[
            html.Div(className='mnid-card', children=[
                html.Div('Equipment & Supplies', className='mnid-card-title'),
                *_rows(supply_inds),
            ]),
            html.Div(className='mnid-card', children=[
                html.Div('Workforce Competency', className='mnid-card-title'),
                *_rows(wf_inds),
            ]),
            html.Div(className='mnid-card', children=[
                html.Div('Data Quality', className='mnid-card-title'),
                *_rows(dq_inds, 'target_pct'),
            ]),
        ]),
    ])


def _compare_status_counts(df: pd.DataFrame, tracked: list) -> dict:
    """Counts indicators by status for a given filtered dataframe."""
    on_tgt = 0
    below  = 0
    no_dat = 0
    for ind in tracked:
        num, den, pct = _cov(df, ind['numerator_filters'], ind['denominator_filters'])
        if den <= 0:
            no_dat += 1
        else:
            if pct >= ind.get('target', 0):
                on_tgt += 1
            else:
                below += 1
    return {'On target': on_tgt, 'Below target': below, 'No data': no_dat}


def _build_compare_pie(title: str, counts: dict) -> go.Figure:
    labels = list(counts.keys())
    values = list(counts.values())
    colors = ['#2563EB', '#0F766E', '#D6D3CB']

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.35,
        marker=dict(colors=colors, line=dict(color='#fff', width=1)),
        textinfo='percent',
        hovertemplate='<b>%{label}</b><br>%{value} indicators (%{percent})<extra></extra>',
    ))
    fig.update_layout(**_CHART_LAYOUT)
    fig.update_layout(
        title=dict(text=title,
                   font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.98),
        height=260,
        margin=dict(l=10, r=10, t=36, b=10),
        legend=dict(orientation='h', x=0, y=-0.08, xanchor='left',
                    font=dict(size=9, color=DIM)),
    )
    return fig


def _build_compare_bar(title: str, counts: dict) -> go.Figure:
    labels = list(counts.keys())
    values = list(counts.values())
    colors = ['#2563EB', '#0F766E', '#D6D3CB']

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation='h',
        marker=dict(color=colors, line=dict(color='#fff', width=1)),
        text=[str(v) for v in values],
        textposition='auto',
        hovertemplate='<b>%{y}</b>: %{x} indicators<extra></extra>',
    ))
    fig.update_layout(**_CHART_LAYOUT)
    fig.update_layout(
        title=dict(text=title,
                   font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.98),
        height=260,
        margin=dict(l=10, r=100, t=36, b=10),
        xaxis=dict(title='Indicators', showgrid=True, gridcolor=GRID_C),
        yaxis=dict(showgrid=False),
    )
    return fig


def _build_compare_heatmap(title: str, df: 'pd.DataFrame', tracked: list) -> go.Figure:
    """Single-entity heatmap: one row per indicator showing coverage %."""
    names, pcts, colors_list = [], [], []
    heat_palette = ['#DBEAFE', '#93C5FD', '#60A5FA', '#2563EB', '#1D4ED8']
    for ind in tracked:
        label = ind.get('label', ind.get('id', '-'))
        if df.empty:
            pct = 0.0
        else:
            _, _, pct = _cov(df, ind['numerator_filters'], ind['denominator_filters'])
        names.append(label[:38])
        pcts.append(_display_pct(pct))
        if pct == 0:
            colors_list.append('#E5E7EB')
        else:
            bucket = min(int((_display_pct(pct) or 0) // 20), len(heat_palette) - 1)
            colors_list.append(heat_palette[bucket])

    if not names:
        fig = go.Figure()
        fig.update_layout(**_CHART_LAYOUT, height=260)
        return fig

    fig = go.Figure(go.Bar(
        x=pcts,
        y=names,
        orientation='h',
        marker=dict(color=colors_list, line=dict(color='#fff', width=0.5)),
        text=[f'{_display_pct(p):.0f}%' for p in pcts],
        textposition='auto',
        hovertemplate='<b>%{y}</b><br>Coverage: %{x:.1f}%<extra></extra>',
    ))
    fig.update_layout(**_CHART_LAYOUT)
    fig.update_layout(
        title=dict(text=title,
                   font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.98),
        height=max(260, len(names) * 24 + 60),
        margin=dict(l=10, r=20, t=36, b=10),
        xaxis=dict(title='Coverage %', range=[0, 100], showgrid=True, gridcolor=GRID_C),
        yaxis=dict(showgrid=False, autorange='reversed'),
    )
    return fig


# comparative analysis section

def _comparative_analysis_section(indicators: list, facility_code: str,
                                  mch_full: pd.DataFrame) -> html.Div:
    """Time-aware comparison across selected facilities or districts and indicators."""
    tracked = [i for i in indicators if i.get('status') == 'tracked']
    all_facs  = sorted(mch_full['Facility_CODE'].dropna().astype(str).unique().tolist()) if len(mch_full) and 'Facility_CODE' in mch_full.columns else sorted(_ALL_FACILITIES[:])
    all_dists = sorted(mch_full['District'].dropna().astype(str).unique().tolist()) if len(mch_full) and 'District' in mch_full.columns else sorted(_ALL_DISTRICTS[:])
    current_dist = _FACILITY_DISTRICT.get(facility_code, '')
    fac_opts = [{'label': _FACILITY_NAMES.get(f, f), 'value': f} for f in all_facs]
    dist_opts = [{'label': d, 'value': d} for d in all_dists]
    ind_opts = [{'label': ind['label'], 'value': ind['id']} for ind in tracked]
    default_facs = ([facility_code] if facility_code in all_facs else all_facs[:4]) or []
    default_dists = ([current_dist] if current_dist in all_dists else all_dists[:4]) or []
    default_inds = [ind['id'] for ind in tracked[:3]]
    _lbl_style = {
        'fontSize': '11px', 'fontWeight': '600', 'color': '#94A3B8',
        'textTransform': 'uppercase', 'letterSpacing': '0.05em',
        'marginBottom': '5px', 'display': 'block',
    }

    compare_card = html.Div(className='mnid-chart-card mnid-compare-card', children=[
        # -- Header row -----------------------------------------------------------
        html.Div(className='mnid-compare-header', style={'display': 'flex', 'alignItems': 'center',
                        'justifyContent': 'space-between',
                        'marginBottom': '16px', 'flexWrap': 'wrap', 'gap': '10px'}, children=[
            html.Div('COMPARISON ANALYSIS', className='mnid-card-title',
                     style={'marginBottom': '0'}),
            html.Div(className='mnid-compare-mode', style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'flexWrap': 'wrap'}, children=[
                html.Span('Compare by:', style={'fontSize': '11px', 'color': '#94A3B8',
                                                'fontWeight': '600', 'letterSpacing': '0.04em'}),
                dcc.RadioItems(
                    id='mnid-compare-mode',
                    options=[
                        {'label': 'Facility', 'value': 'facility'},
                        {'label': 'District', 'value': 'district'},
                    ],
                    value='facility',
                    inline=True,
                    inputStyle={'marginRight': '5px'},
                    labelStyle={'marginRight': '16px', 'fontSize': '12px',
                                'color': '#E2E8F0', 'cursor': 'pointer', 'fontWeight': '600'},
                ),
                html.Button(
                    id='mnid-compare-chart-toggle',
                    className='mnid-trend-toggle is-bar',
                    n_clicks=0,
                    type='button',
                    children=[
                        html.Span('Bar', id='mnid-compare-chart-toggle-text', className='mnid-trend-toggle-text'),
                        html.Span(className='mnid-trend-toggle-thumb'),
                    ],
                ),
            ]),
        ]),
        html.Div(className='mnid-compare-filters', style={'display': 'grid', 'gridTemplateColumns': '1.4fr 0.8fr 1.2fr', 'gap': '12px', 'marginBottom': '14px'}, children=[
            html.Div(children=[
                html.Label('Locations', style=_lbl_style),
                dcc.Dropdown(
                    id='mnid-compare-entities',
                    options=fac_opts,
                    value=default_facs,
                    multi=True,
                    placeholder='Select locations...',
                ),
            ]),
            html.Div(children=[
                html.Label('Time Grain', style=_lbl_style),
                dcc.Dropdown(
                    id='mnid-compare-time-grain',
                    options=[
                        {'label': 'Monthly', 'value': 'monthly'},
                        {'label': 'Quarterly', 'value': 'quarterly'},
                        {'label': 'Yearly', 'value': 'yearly'},
                    ],
                    value='monthly',
                    clearable=False,
                ),
            ]),
            html.Div(children=[
                html.Label('Indicators', style=_lbl_style),
                dcc.Dropdown(
                    id='mnid-compare-indicators',
                    options=ind_opts,
                    value=default_inds,
                    multi=True,
                    placeholder='Select up to 3 indicators...',
                ),
            ]),
        ]),
        # -- Grouped bar chart ----------------------------------------------------
        dcc.Graph(
            id='mnid-compare-bar-chart',
            config={
                'displayModeBar': 'hover',
                'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'],
                'toImageButtonOptions': {'format': 'png', 'scale': 2},
            },
            className='mnid-compare-chart',
            style={'height': '420px'},
        ),
    ])

    return html.Div(id='mnid-comparative', children=[
        dcc.Store(id='mnid-compare-store', data={
            'tracked':    tracked,
            'records':    _serialize_store_df(mch_full),
            'facility_options': fac_opts,
            'district_options': dist_opts,
            'current_fac': facility_code,
            'current_dist': current_dist,
        }),
        dcc.Store(id='mnid-compare-chart-type-store', data='bar'),
        html.Div(className='mnid-chart-grid', children=[compare_card]),
    ])


# # MNID table header style
_TH = {
    'fontSize': '10px', 'fontWeight': '700', 'color': MUTED,
    'textTransform': 'uppercase', 'letterSpacing': '0.06em',
    'padding': '8px 10px', 'borderBottom': f'2px solid #E2E8F0',
    'textAlign': 'left', 'whiteSpace': 'nowrap',
    'background': '#FAFAFA',
}


# # MNID hero indicator donut row

def _hero_donut_card(label, pct, target, color):
    """Large CSS conic-gradient donut card for a single indicator."""
    p = max(0.0, min(float(pct), 100.0))
    r_v = int(color[1:3], 16)
    g_v = int(color[3:5], 16)
    b_v = int(color[5:7], 16)
    cls = _css(p, target)
    badge_map = {
        'ok':     ('#F0FDF4', '#14532D', '#BBF7D0', 'On target'),
        'warn':   ('#FFFBEB', '#92400E', '#FDE68A', 'Performing'),
        'danger': ('#FEF2F2', '#7F1D1D', '#FECACA', 'Needs review'),
    }
    bg, fg, border, txt = badge_map.get(cls, badge_map['danger'])

    return html.Div(className='mnid-hero-card', children=[
        html.Div(style={
            'width': '120px', 'height': '120px', 'borderRadius': '50%',
            'background': f'conic-gradient({color} {p:.1f}%, {GRID_C} 0)',
            'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
            'margin': '0 auto 10px',
            'filter': (
                'drop-shadow(0 4px 14px rgba(226,232,240,0.5))'
                if p == 0
                else f'drop-shadow(0 4px 14px rgba({r_v},{g_v},{b_v},0.28))'
            ),
        }, children=[
            html.Div(style={
                'width': '84px', 'height': '84px', 'borderRadius': '50%',
                'background': '#fff',
                'display': 'flex', 'flexDirection': 'column',
                'alignItems': 'center', 'justifyContent': 'center',
            }, children=[
                html.Span(f'{_display_pct(p):.0f}%', style={
                    'fontSize': '24px', 'fontWeight': '800',
                    'color': color, 'lineHeight': '1',
                }),
                html.Span(f'Target {target}%', style={
                    'fontSize': '8px', 'color': MUTED,
                    'lineHeight': '1.3', 'marginTop': '3px',
                }),
            ]),
        ]),
        html.Div(label, className='mnid-hero-label'),
        html.Span(txt, style={
            'background': bg, 'color': fg, 'border': f'1px solid {border}',
            'fontSize': '9px', 'fontWeight': '600',
            'padding': '2px 8px', 'borderRadius': '10px',
            'display': 'inline-block', 'marginTop': '5px',
        }),
    ])


def _hero_donut_row(computed, preferred_cat: str = 'ANC', section_title: str | None = None):
    """Row of large hero donut cards favouring the requested category first."""
    preferred = [c for c in computed if c.get('category') == preferred_cat]
    heroes = preferred[:5] if preferred else computed[:5]
    if not heroes:
        return html.Div()

    if not section_title:
        label = _CAT_LABELS.get(preferred_cat, str(preferred_cat or 'Program'))
        section_title = f'KEY {label.upper()} INDICATORS'

    cards = []
    for ind in heroes:
        color = _cov_color(ind['pct'])
        cards.append(_hero_donut_card(ind['label'], ind['pct'], ind['target'], color))

    return html.Div(style={'marginBottom': '12px'}, children=[
        html.Div(section_title, className='mnid-section-lbl'),
        html.Div(className='mnid-hero-row', children=cards),
    ])


# # MNID priority indicators status table

def _priority_table(computed):
    """Priority Indicators Status table with progress bars and status badges."""
    if not computed:
        return html.Div()

    sorted_c = sorted(computed, key=lambda x: (
        0 if x['pct'] < x['target'] * 0.85 else (1 if x['pct'] < x['target'] else 2),
        -x['pct'],
    ))

    def _badge(cls):
        conf = {
            'ok':     ('#F0FDF4', '#14532D', '#BBF7D0', 'On target'),
            'warn':   ('#FFFBEB', '#92400E', '#FDE68A', 'Performing'),
            'danger': ('#FEF2F2', '#7F1D1D', '#FECACA', 'Needs review'),
        }.get(cls, ('#FEF2F2', '#7F1D1D', '#FECACA', 'Needs review'))
        bg, fg, bdr, lbl = conf
        return html.Span(lbl, style={
            'background': bg, 'color': fg, 'border': f'1px solid {bdr}',
            'fontSize': '9px', 'fontWeight': '600',
            'padding': '2px 8px', 'borderRadius': '10px', 'whiteSpace': 'nowrap',
        })

    def _prog(pct, target):
        fill = min(pct, 100)
        col  = {'ok': OK_C, 'warn': WARN_C, 'danger': DANGER_C}.get(_css(pct, target), MUTED)
        return html.Div(style={
            'position': 'relative', 'height': '6px',
            'background': GRID_C, 'borderRadius': '3px', 'minWidth': '90px',
        }, children=[
            html.Div(style={
                'width': f'{fill:.0f}%', 'height': '100%',
                'background': col, 'borderRadius': '3px',
                'transition': 'width 0.4s ease',
            }),
            html.Div(style={
                'position': 'absolute', 'top': '-3px',
                'left': f'{min(target, 100)}%',
                'height': '12px', 'width': '1.5px',
                'background': '#94A3B8', 'transform': 'translateX(-50%)',
                'borderRadius': '1px',
            }),
        ])

    cat_dot = {
        'ANC':     CAT_PALETTES['ANC'][0],
        'Labour':  CAT_PALETTES['Labour'][0],
        'Newborn': CAT_PALETTES['Newborn'][0],
        'PNC':     CAT_PALETTES['PNC'][0],
    }

    rows = []
    for ind in sorted_c:
        cls = _css(ind['pct'], ind['target'])
        val_col = {'ok': OK_C, 'warn': WARN_C, 'danger': DANGER_C}.get(cls, TEXT)
        dot_col = cat_dot.get(ind.get('category', ''), MUTED)
        rows.append(html.Tr(style={'borderBottom': f'1px solid {GRID_C}'}, children=[
            html.Td(style={'padding': '8px 10px'}, children=[
                html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '8px'},
                         children=[
                    html.Div(style={'width': '7px', 'height': '7px', 'borderRadius': '50%',
                                    'background': dot_col, 'flexShrink': '0'}),
                    html.Span(ind['label'], style={'fontSize': '11px', 'color': DIM,
                                                   'lineHeight': '1.3'}),
                ]),
            ]),
            html.Td(f"{ind['pct']:.0f}%", style={
                'fontSize': '14px', 'fontWeight': '700', 'color': val_col,
                'padding': '8px 10px', 'textAlign': 'center',
            }),
            html.Td(f"{ind['target']}%", style={
                'fontSize': '11px', 'color': MUTED,
                'padding': '8px 10px', 'textAlign': 'center',
            }),
            html.Td(_prog(ind['pct'], ind['target']),
                    style={'padding': '8px 10px', 'minWidth': '100px'}),
            html.Td(_badge(cls), style={'padding': '8px 10px'}),
        ]))

    return html.Div(className='mnid-card', style={'marginBottom': '14px'}, children=[
        html.Div('PRIORITY INDICATORS STATUS', className='mnid-section-lbl'),
        html.Div(style={'overflowX': 'auto'}, children=[
            html.Table(className='mnid-priority-tbl', children=[
                html.Thead(html.Tr([
                    html.Th('Indicator Name', style=_TH),
                    html.Th('Coverage',       style={**_TH, 'textAlign': 'center'}),
                    html.Th('Target',         style={**_TH, 'textAlign': 'center'}),
                    html.Th('Progress',       style={**_TH, 'minWidth': '100px'}),
                    html.Th('Status',         style=_TH),
                ])),
                html.Tbody(rows),
            ]),
        ]),
    ])


# # MNID district speedometer gauges

def _district_gauge_fig(pct, district):
    """Plotly Indicator speedometer gauge for a single district."""
    val   = _display_pct(pct) if pct is not None else 0
    color = _cov_color(pct) if pct is not None else MUTED
    fig   = go.Figure(go.Indicator(
        mode  = 'gauge+number',
        value = val,
        number = dict(suffix='%', font=dict(size=30, color=color, family=FONT)),
        title  = dict(text=f'<b>{district}</b>',
                      font=dict(size=13, color=TEXT, family=FONT)),
        gauge  = dict(
            axis=dict(range=[0, 100], tickwidth=1, tickcolor=BORDER,
                      tickfont=dict(size=9, color=MUTED), dtick=25),
            bar=dict(color=color, thickness=0.28),
            bgcolor=GRID_C,
            borderwidth=0,
            steps=[
                dict(range=[0,   40],  color='#FEF2F2'),
                dict(range=[40,  65],  color='#FFFBEB'),
                dict(range=[65,  88],  color='#F0FDF4'),
                dict(range=[88, 100],  color='#DCFCE7'),
            ],
            threshold=dict(
                line=dict(color='#64748B', width=2),
                thickness=0.75, value=80,
            ),
        ),
    ))
    fig.update_layout(
        paper_bgcolor=BG,
        font=dict(family=FONT),
        height=200,
        margin=dict(l=16, r=16, t=52, b=8),
    )
    return fig


def _build_district_gauge_row(store, year='All years'):
    """District performance overview: speedometers for <=5 districts, bar chart for >5."""
    avgs      = store.get('district_avgs', {}).get(year, {})
    districts = store.get('all_districts', [])
    data      = [(d, avgs[d]) for d in districts if avgs.get(d) is not None]
    if not data:
        return html.Div()

    def _status_text(pct):
        if pct >= 80:  return 'Strong performance'
        if pct >= 65:  return 'Moderate coverage'
        return 'Needs attention'

    if len(data) <= 5:
        cards = []
        for dist, pct in data:
            color = _cov_color(pct)
            fig   = _district_gauge_fig(pct, dist)
            cards.append(html.Div(className='mnid-district-gauge-card', children=[
                dcc.Graph(figure=fig,
                          config={'displayModeBar': 'hover',
                                  'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                                  'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                          style={'height': '200px'}),
                html.Div(_status_text(pct), style={
                    'fontSize': '10px', 'color': color,
                    'fontWeight': '600', 'marginTop': '-6px', 'paddingBottom': '4px',
                }),
            ]))
        inner = html.Div(className='mnid-grid3', children=cards)
    else:
        # Horizontal bar chart - sorted ascending so worst performer is at top
        sorted_data = sorted(data, key=lambda x: x[1])
        dists  = [d for d, _ in sorted_data]
        vals   = [_display_pct(v) for _, v in sorted_data]
        colors = [_cov_color(v) for v in vals]
        bar_h  = max(260, len(dists) * 24 + 40)

        fig = go.Figure(go.Bar(
            x=vals, y=dists,
            orientation='h',
            marker=dict(color=colors, line=dict(color='rgba(0,0,0,0)', width=0)),
            text=[f'{v:.0f}%' for v in vals],
            textposition='outside',
            textfont=dict(size=10, family=FONT),
            hovertemplate='<b>%{y}</b><br>Avg Coverage: %{x:.1f}%<extra></extra>',
        ))
        fig.add_vline(x=80, line_dash='dash', line_color=WARN_C, line_width=1.5,
                      annotation_text='Target 80%', annotation_font_size=9,
                      annotation_font_color=WARN_C, annotation_position='top right')
        fig.update_layout(
            paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family=FONT, size=10),
            height=bar_h,
            margin=dict(l=8, r=60, t=12, b=24),
            xaxis=dict(
                range=[0, 110], showgrid=True, gridcolor=GRID_C, gridwidth=0.5,
                title=dict(text='Avg Coverage %', font=dict(size=9)),
                tickfont=dict(size=9),
            ),
            yaxis=dict(showgrid=False, tickfont=dict(size=10)),
        )
        inner = dcc.Graph(
            figure=fig,
            config={'displayModeBar': False},
            style={'height': f'{bar_h}px'},
        )

    return html.Div(style={'marginBottom': '14px'}, children=[
        html.Div('DISTRICT PERFORMANCE OVERVIEW', className='mnid-section-lbl'),
        inner,
    ])


# # MNID PPH management cascade funnel

def _pph_cascade(df):
    """PPH Management Cascade funnel chart."""
    try:
        def _n(col, val, col2=None, val2=None):
            if col not in df.columns:
                return 0
            mask = df[col].fillna('').str.upper().str.contains(val.upper(), na=False)
            sub  = df[mask]
            if col2 and val2 and col2 in sub.columns:
                sub = sub[sub[col2] == val2]
            return int(sub['person_id'].nunique())

        labor_n = _n('Encounter', 'LABOUR|DELIVERY|BIRTH')
        if labor_n == 0:
            return None

        stages = [
            ('Women in Labor',          labor_n),
            ('PPH Screening Performed', _n('concept_name', 'PPH screening')),
            ('PPH Detected',            _n('concept_name', 'PPH screening',
                                          'obs_value_coded', 'Positive')),
            ('Treatment Bundle',        _n('concept_name', 'PPH treatment bundle')),
        ]
        labels = [s[0] for s in stages]
        values = [s[1] for s in stages]

        if sum(values[1:]) == 0:
            return None

        colors = ['#2563EB', '#7C3AED', '#C2410C', '#0F766E']

        fig = go.Figure(go.Funnel(
            y=labels, x=values,
            textinfo='value+percent initial',
            textfont=dict(size=11, family=FONT),
            marker=dict(color=colors, line=dict(color=['#fff'] * 4, width=2)),
            connector=dict(line=dict(color=GRID_C, width=2)),
            hovertemplate='<b>%{y}</b><br>Count: %{x:,}<extra></extra>',
        ))
        fig.update_layout(
            **_CHART_LAYOUT,
            title=dict(text='PPH Management Cascade',
                       font=dict(size=12, color='#444441', family=FONT),
                       x=0, xanchor='left', y=0.98),
            height=280,
            margin=dict(l=8, r=8, t=36, b=8),
            showlegend=False,
        )
        return html.Div(className='mnid-chart-card', children=[
            dcc.Graph(figure=fig,
                      config={'displayModeBar': 'hover',
                              'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'],
                              'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                      style={'height': '280px'}),
        ])
    except Exception:
        return None


# MNID header, alert, KPI, and section navigation components

def _topbar(facility, period, n_tracked, n_await, facility_df=None, network_df=None,
            title='Maternal and Child Health Indicators', subtitle='Clean view of performance, comparison, coverage, and readiness.',
            theme='default'):
    facility_name = _FACILITY_NAMES.get(facility, facility or 'Network view')
    district = _FACILITY_DISTRICT.get(facility, 'All districts')

    source_df = facility_df if facility_df is not None and len(facility_df) else network_df
    if source_df is not None and len(source_df):
        if facility and 'Facility_CODE' in source_df.columns:
            fac_rows = source_df[source_df['Facility_CODE'].astype(str) == str(facility)]
        else:
            fac_rows = source_df
            facility_name = 'Network view' if len(source_df) else facility_name
            district = 'All districts' if len(source_df) else district
        if len(fac_rows):
            if 'Facility' in fac_rows.columns:
                names = fac_rows['Facility'].dropna().astype(str)
                if not names.empty:
                    facility_name = names.mode().iloc[0]
            if 'District' in fac_rows.columns:
                dists = fac_rows['District'].dropna().astype(str)
                if not dists.empty:
                    district = dists.mode().iloc[0]

    selected_program = 'Neonatal Care' if theme == 'newborn' else 'All'
    if facility_df is not None:
        requested = getattr(facility_df, 'attrs', {}).get('mnid_program')
        if requested and theme != 'newborn':
            selected_program = requested

    topbar_label = 'N-NID Dashboard' if theme == 'newborn' else 'M-NID Dashboard'
    newborn_focus = None
    if theme == 'newborn':
        newborn_focus = html.Div(className='mnid-topbar-highlight', children=[
            html.Div(className='mnid-topbar-highlight-copy', children=[
                html.Div('Neonatal service overview', className='mnid-topbar-highlight-title'),
                html.Div('View stabilization, respiratory support, KMC uptake, and facility performance in one place.',
                         className='mnid-topbar-highlight-subtitle'),
            ]),
            html.Div(className='mnid-topbar-highlight-chips', children=[
                html.Span('Stabilize', className='mnid-topbar-chip'),
                html.Span('Support', className='mnid-topbar-chip'),
                html.Span('Monitor', className='mnid-topbar-chip'),
                html.Span('Benchmark', className='mnid-topbar-chip'),
                html.Span(f'{n_tracked} available', className='mnid-topbar-chip strong'),
                html.Span(f'{n_await} pending', className='mnid-topbar-chip subtle'),
            ]),
        ])

    return html.Div(className=f'mnid-topbar{" mnid-topbar-newborn" if theme == "newborn" else ""}', children=[
        html.Div(className='mnid-topbar-copy', children=[
            html.Div(topbar_label, className='mnid-topbar-label'),
            html.H1(title),
            html.P(subtitle),
            newborn_focus,
        ]),
        html.Div(className='mnid-info-pills', children=[
            html.Div(className='mnid-info-pill', children=[
                html.Div('Facility', className='mnid-info-pill-label'),
                html.Div(facility_name, className='mnid-info-pill-value'),
            ]),
            html.Div(className='mnid-info-pill', children=[
                html.Div('District', className='mnid-info-pill-label'),
                html.Div(district, className='mnid-info-pill-value'),
            ]),
            html.Div(className='mnid-info-pill', children=[
                html.Div('Period', className='mnid-info-pill-label'),
                html.Div(period,
                         style={'fontSize': '11px', 'fontWeight': '700',
                                'color': TEXT, 'lineHeight': '1.2'}),
            ]),
            html.Div(className='mnid-info-pill', children=[
                html.Div('Program', className='mnid-info-pill-label'),
                html.Div(
                    'Labour & Delivery' if selected_program == 'Labour' else selected_program,
                    className='mnid-info-pill-value mnid-info-pill-value-compact',
                ),
            ]),
            html.Div(className='mnid-info-pill', children=[
                html.Div('Indicators', className='mnid-info-pill-label'),
                html.Div(f'{n_tracked} available / {n_await} pending',
                         style={'fontSize': '11px', 'fontWeight': '700',
                                'color': TEXT, 'lineHeight': '1.2'}),
            ]),
        ]),
    ])


def _sidebar(facility_code: str, theme: str = 'default') -> html.Div:
    if theme == 'newborn':
        nav_items = [
            ('Overview', '#mnid-summary'),
            ('Service Delivery', '#mnid-data-tables'),
            ('Patient Trends & Outcomes', '#mnid-trends'),
            ('District Performance', '#mnid-performance'),
            ('Geographic Coverage', '#mnid-heatmap'),
            ('Coverage & Quality', '#mnid-coverage'),
            ('Facility Comparison', '#mnid-comparative'),
            ('Clinical Interventions', '#mnid-analysis'),
            ('Operational Readiness', '#mnid-readiness'),
        ]
    else:
        nav_items = [
            ('Overview', '#mnid-summary'),
            ('Data Tables', '#mnid-data-tables'),
            ('Trend', '#mnid-trends'),
            ('Performance', '#mnid-performance'),
            ('Map View', '#mnid-heatmap'),
            ('Indicators', '#mnid-coverage'),
            ('Comparison', '#mnid-comparative'),
            ('Analysis', '#mnid-analysis'),
            ('Readiness', '#mnid-readiness'),
        ]
    return html.Div(className='mnid-nav', children=[
        html.A(
            id={'type': 'mnid-nav-btn', 'index': href},
            href=href,
            className='mnid-nav-btn active' if index == 0 else 'mnid-nav-btn',
            children=label,
        )
        for index, (label, href) in enumerate(nav_items)
    ])


def _alert_banner(below, strong):
    if not below:
        return html.Div(className='mnid-alert mnid-alert-ok', children=[
            html.Div(className='mnid-alert-icon',
                     children=html.Span('OK', style={'color':'#fff','fontSize':'9px',
                                                     'fontWeight':'700'})),
            html.P([html.Strong('On track. '),
                    'All available indicators are meeting target.']),
        ])
    below_txt = ', '.join(f'{n} ({_display_pct(p):.0f}%)' for n, p in below)
    strong_txt = ', '.join(strong[:3]) or 'None'
    return html.Div(className='mnid-alert', children=[
        html.Div(className='mnid-alert-icon',
                 children=html.Span('!', style={'color': '#fff', 'fontSize': '10px',
                                                'fontWeight': '700'})),
        html.P([html.Strong('Needs attention. '),
                f'Below target: {below_txt}. Strong areas: {strong_txt}.']),
    ])


def _avg_ring(pct: float, color: str) -> html.Div:
    """Prominent donut ring - the ring IS the value display for avg coverage card."""
    p = max(0.0, min(pct, 100.0))
    # Choose font size based on length
    font_size = '11px' if p < 100 else '9px'
    return html.Div(style={
        'width': '62px', 'height': '62px', 'borderRadius': '50%',
        'background': f'conic-gradient({color} {p:.1f}%, {GRID_C} 0)',
        'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
        'flexShrink': '0',
        'filter': 'drop-shadow(0 2px 6px rgba(0,0,0,0.10))',
    }, children=[
        html.Div(style={
            'width': '44px', 'height': '44px', 'borderRadius': '50%',
            'background': BG,
            'display': 'flex', 'flexDirection': 'column',
            'alignItems': 'center', 'justifyContent': 'center',
            'gap': '1px',
        }, children=[
            html.Span(f'{_display_pct(p):.0f}%', style={
                'fontSize': font_size, 'fontWeight': '700',
                'color': color, 'lineHeight': '1',
            }),
            html.Span('avg', style={
                'fontSize': '7px', 'color': MUTED, 'lineHeight': '1',
            }),
        ]),
    ])


def _count_bar(count: int, total: int, color: str) -> html.Div:
    """Thin coloured bottom stripe showing proportion of total."""
    fill = round(count / total * 100) if total else 0
    return html.Div(style={
        'position': 'absolute', 'bottom': '0', 'left': '0', 'right': '0',
        'height': '3px', 'background': GRID_C, 'borderRadius': '0 0 10px 10px',
    }, children=[
        html.Div(style={
            'width': f'{fill}%', 'height': '100%',
            'background': color, 'borderRadius': '0 0 0 10px',
            'transition': 'width 0.5s ease',
        }),
    ])


def _kpi(label, value, sub, cls, bottom_bar=None, ring=None):
    return html.Div(className=f'mnid-kpi {cls}', children=[
        html.Div(style={'display': 'flex', 'justifyContent': 'space-between',
                        'alignItems': 'flex-start', 'gap': '6px'}, children=[
            html.Div([
                html.Div(label, className='kpi-lbl'),
                html.Div(value, className='kpi-val'),
                html.Div(sub,   className='kpi-sub'),
            ]),
            ring or html.Div(),
        ]),
        bottom_bar or html.Div(),
    ])


def _kpi_row(computed):
    n    = len(computed)
    on   = [c for c in computed if c['pct'] >= c['target']]
    mon  = [c for c in computed if c['target'] * .85 <= c['pct'] < c['target']]
    crit = [c for c in computed if c['pct'] < c['target'] * .85]
    avg  = round(sum(c['pct'] for c in computed) / n, 1) if n else 0.0
    avg_color = _cov_color(avg)
    return html.Div(className='mnid-kpi-row', children=[
        _kpi('Available Indicators', str(n), 'live indicators', 'info',
             bottom_bar=_count_bar(n, n, INFO_C)),
        _kpi('On Target', str(len(on)), 'meeting benchmark', 'ok',
             bottom_bar=_count_bar(len(on), n, OK_C)),
        _kpi('Watch', str(len(mon)), 'near target', 'warn',
             bottom_bar=_count_bar(len(mon), n, WARN_C)),
        _kpi('Needs Review', str(len(crit)), 'below target', 'danger',
             bottom_bar=_count_bar(len(crit), n, DANGER_C)),
        _kpi('Average Coverage', '', 'across available indicators', 'info',
             ring=_avg_ring(avg, avg_color)),
    ])



# MNID section anchor helper

def _section_anchor(anchor_id):
    """Invisible offset anchor for sticky-nav scrolling."""
    return html.Div(id=anchor_id, className='mnid-section-anchor')


# MNID dashboard entry point

def render_mnid_dashboard(filtered, data_opd, delta_days, config,
                          facility_code, start_date, end_date,
                          scope_meta: dict | None = None):
    facility_df = _prepare_mnid_dataframe(filtered)
    network_df = _prepare_mnid_dataframe(data_opd)
    selected_program = (scope_meta or {}).get('mnid_categories')
    selected_program = selected_program[0] if selected_program else 'All'
    facility_df.attrs['mnid_program'] = selected_program
    network_df.attrs['mnid_program'] = selected_program
    if network_df.empty:
        network_df = facility_df.copy()

    vt          = config.get('visualization_types', {})
    all_inds    = config.get('priority_indicators') or vt.get('priority_indicators', [])
    supply_inds = config.get('supply_indicators') or vt.get('supply_indicators', [])
    wf_inds     = config.get('workforce_indicators') or vt.get('workforce_indicators', [])
    dq_inds     = config.get('data_quality_indicators') or vt.get('data_quality_indicators', [])
    period      = f'{start_date} to {end_date}'

    requested_categories = (scope_meta or {}).get('mnid_categories')
    category_order = _resolve_category_order(all_inds, requested_categories or config.get('mnid_categories'))
    if category_order:
        allowed = set(category_order)
        all_inds = [i for i in all_inds if i.get('category') in allowed]

    tracked  = [i for i in all_inds if i.get('status') == 'tracked']
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
    hero_title = 'KEY NEONATAL INDICATORS' if dashboard_theme == 'newborn' else f'KEY {_CAT_LABELS.get(default_cat, str(default_cat or "Program")).upper()} INDICATORS'

    computed = []
    for ind in tracked:
        num, den, pct = _cov(facility_df, ind['numerator_filters'],
                              ind['denominator_filters'])
        computed.append({**ind, 'pct': pct, 'numerator': num, 'denominator': den})

    below  = [(c['label'], c['pct']) for c in computed if c['pct'] < c['target']]
    strong = [c['label'] for c in computed if c['pct'] >= c['target']]

    by_cat = {}
    for ind in all_inds:
        by_cat.setdefault(ind.get('category','Other'), []).append(ind)

    coverage_charts  = _coverage_charts_section(by_cat, facility_df, category_order)

    # Pre-build analysis charts
    anc_charts    = _anc_charts(facility_df)
    labour_charts = _labour_charts(facility_df)
    pnc_charts    = _pnc_charts(facility_df)
    nb_charts     = _newborn_charts(facility_df)

    # All accordion sections open by default
    analysis_acc = [
        _chart_acc_section('ch_anc',    'Antenatal Care',    anc_charts)    if anc_charts and 'ANC' in category_order else None,
        _chart_acc_section('ch_labour', 'Labour & Delivery', labour_charts) if labour_charts and 'Labour' in category_order else None,
        _chart_acc_section('ch_pnc',    'Postnatal Care',    pnc_charts)    if pnc_charts and 'PNC' in category_order else None,
        _chart_acc_section('ch_nb',     'Neonatal Care',     nb_charts)     if nb_charts and 'Newborn' in category_order else None,
    ]
    analysis_acc = [a for a in analysis_acc if a]

    performance_div, heatmap_div = _coverage_heatmap_section(all_inds, facility_code, network_df)
    service_table_div = _service_table_switcher(facility_df, category_order, default_cat, scope_meta)
    comparative_div  = _comparative_analysis_section(all_inds, facility_code, network_df)

    def _sec_header(title, count=None, desc=None, eyebrow=None):
        return html.Div(className=f'mnid-section-header{" mnid-section-header-newborn" if dashboard_theme == "newborn" else ""}', children=[
            html.Div([
                html.Div(eyebrow, className='mnid-section-header-eyebrow') if eyebrow else None,
                html.Span(title, className='mnid-section-header-title'),
                html.Div(desc, className='mnid-section-header-desc') if desc else None,
            ]),
            html.Span(f'{count} indicators' if count else '',
                      className='mnid-section-header-count'),
        ])

    total_analysis = sum(
        len(charts) for cat, charts in [
            ('ANC', anc_charts),
            ('Labour', labour_charts),
            ('PNC', pnc_charts),
            ('Newborn', nb_charts),
        ] if cat in category_order
    )

    main_content = html.Div(className=f'mnid-main{" mnid-main-newborn" if dashboard_theme == "newborn" else ""}', children=[

        _topbar(facility_code, period, len(tracked), len(awaiting), facility_df=facility_df, network_df=network_df, title=dashboard_title, subtitle=dashboard_subtitle, theme=dashboard_theme),
        _sidebar(facility_code, theme=dashboard_theme),
        _alert_banner(below, strong),

        _section_anchor('mnid-summary'),
        _sec_header('Overview',
                    desc='Neonatal program snapshot, priority indicator posture, and facility context.' if dashboard_theme == 'newborn' else f'{len(tracked)} available - {len(awaiting)} awaiting',
                    eyebrow='Overview' if dashboard_theme == 'newborn' else None),
        _kpi_row(computed),
        _hero_donut_row(computed, preferred_cat=default_cat, section_title=hero_title),
        _priority_table(computed),

        _section_anchor('mnid-data-tables'),
        _sec_header('Service Delivery' if dashboard_theme == 'newborn' else 'Data Tables',
                    desc='Structured service counts for admissions, thermal care, respiratory support, KMC, and newborn outcomes.' if dashboard_theme == 'newborn' else 'Key service counts and outcomes',
                    eyebrow='Service Summary' if dashboard_theme == 'newborn' else None),
        service_table_div,

        _section_anchor('mnid-trends'),
        _sec_header('Patient Trends & Outcomes' if dashboard_theme == 'newborn' else 'Coverage Trends',
                    desc='Monthly trends for neonatal admissions and outcome-related indicators, with target references where applicable.' if dashboard_theme == 'newborn' else '12-month rolling - dotted line = target',
                    eyebrow='Trends' if dashboard_theme == 'newborn' else None),
        _trend_switcher(facility_df, all_inds, scope_meta=scope_meta),

        _section_anchor('mnid-performance'),
        _sec_header('District Performance' if dashboard_theme == 'newborn' else 'Facility Performance',
                    desc='How this newborn service compares across district and facility peers.' if dashboard_theme == 'newborn' else 'District comparison heatmap for key performance indicators',
                    eyebrow='Performance' if dashboard_theme == 'newborn' else None),
        performance_div,

        _section_anchor('mnid-heatmap'),
        _sec_header('Geographic Coverage' if dashboard_theme == 'newborn' else 'Map View',
                    desc='Geographic context for neonatal service delivery and district-level performance.' if dashboard_theme == 'newborn' else 'Geographic coverage map and district/facility context',
                    eyebrow='Map' if dashboard_theme == 'newborn' else None),
        heatmap_div,

        _section_anchor('mnid-coverage'),
        _sec_header('Coverage & Quality' if dashboard_theme == 'newborn' else 'Coverage Indicators', sum(len(v) for v in by_cat.values()),
                    desc='Coverage against target across the neonatal care pathway, from stabilization to follow-up.' if dashboard_theme == 'newborn' else 'Coverage % vs target - target threshold shown per chart',
                    eyebrow='Indicators' if dashboard_theme == 'newborn' else None),
        coverage_charts,

        _section_anchor('mnid-comparative'),
        _sec_header('Facility Comparison' if dashboard_theme == 'newborn' else 'Facility & District Comparison',
                    desc='Facility and district comparison for neonatal indicators.' if dashboard_theme == 'newborn' else 'Cross-facility and district indicator benchmarking',
                    eyebrow='Comparison' if dashboard_theme == 'newborn' else None),
        comparative_div,

        _section_anchor('mnid-analysis'),
        _sec_header('Clinical Interventions' if dashboard_theme == 'newborn' else 'Clinical Analysis',
                    None if dashboard_theme == 'newborn' else total_analysis,
                    desc='Clinical intervention, thermal support, respiratory support, and complication views.' if dashboard_theme == 'newborn' else 'Care-phase deep-dives',
                    eyebrow='Clinical View' if dashboard_theme == 'newborn' else None),
        dmc.Accordion(
            multiple=True,
            value=[a.value for a in analysis_acc],
            variant='separated', radius='md', mb='md',
            children=analysis_acc,
            styles={
                'item': {'backgroundColor': BG, 'border': f'1px solid {BORDER}',
                         'borderRadius': '12px', 'marginBottom': '8px',
                         'boxShadow': '0 1px 3px rgba(0,0,0,0.04)'},
                'control': {'padding': '12px 16px'},
                'panel': {'padding': '0 16px 2px'},
            },
        ),

        _section_anchor('mnid-readiness'),
        _sec_header('Operational Readiness',
                    desc='Devices, staffing, and data quality conditions that support neonatal care delivery.' if dashboard_theme == 'newborn' else 'Equipment - workforce competency - data quality',
                    eyebrow='Readiness' if dashboard_theme == 'newborn' else None),
        _system_readiness(facility_df, supply_inds, wf_inds, dq_inds),
    ])

    return html.Div(className=f'mnid-bg{" mnid-theme-newborn" if dashboard_theme == "newborn" else ""}', children=[
        # Hidden components used by the MNID scroll spy callback
        dcc.Interval(id='mnid-scrollspy-tick', interval=250, max_intervals=-1),
        dcc.Store(id='mnid-scrollspy-out'),
        html.Div(className=f'mnid-shell{" mnid-shell-newborn" if dashboard_theme == "newborn" else ""}', children=[main_content]),
    ])
