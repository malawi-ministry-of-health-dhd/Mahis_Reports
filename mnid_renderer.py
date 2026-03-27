"""
MNID renderer — professional dashboard layout.
Structure:
  1. Header + sticky nav + Alert
  2. KPI summary row
  3. Collapsible accordion: indicator cards per care phase (clean, no sparklines)
  4. Trend section: single chart with ANC/Labour/Newborn/PNC category switcher
  5. Heatmap: indicator coverage heatmap with multi-view and year-filter buttons
  6. Clinical analysis: themed charts in collapsible accordion sections
  7. System readiness: equipment / workforce / data quality
"""
from dash import html, dcc, clientside_callback, callback, Input, Output, State, ALL
import dash_mantine_components as dmc
from helpers import create_count_from_config
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import json


# palette
OK_C    = '#16A34A';  WARN_C  = '#CA8A04';  DANGER_C = '#DC2626'
INFO_C  = '#15803D';  MUTED   = '#94A3B8';  GRID_C   = '#F1F5F9'
BG      = '#fff';     BORDER  = '#E2E8F0';  TEXT     = '#0F172A'
DIM     = '#64748B';  FONT    = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'

CAT_PALETTES = {
    'ANC':     ['#15803D','#22C55E','#4ADE80','#86EFAC','#BBF7D0','#14532D'],
    'Labour':  ['#BA7517','#D4881A','#E8A830','#F5C658','#FAD97A','#7C4D0A','#A35F10'],
    'Newborn': ['#0D9488','#14B8A6','#2DD4BF','#5EEAD4','#99F6E4','#0F766E','#0E7490'],
    'PNC':     ['#7C3AED','#9D5CF0','#B683F4','#CFAAF8'],
}

HEATMAP_CS = [
    [0.00, '#FEF2F2'],
    [0.40, '#DC2626'],
    [0.65, '#CA8A04'],
    [0.80, '#FDE68A'],
    [0.88, '#BBF7D0'],
    [1.00, '#16A34A'],
]

_CHART_LAYOUT = dict(
    paper_bgcolor=BG, plot_bgcolor=BG,
    font=dict(family=FONT, color=TEXT, size=11),
    margin=dict(l=4, r=4, t=36, b=4),
    hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
    legend=dict(font=dict(size=10, color=DIM), bgcolor='rgba(0,0,0,0)',
                orientation='v', x=1.02, y=0.5, xanchor='left'),
)

# Facility metadata
_FACILITY_DISTRICT = {
    'LL040033': 'Lilongwe',
    'MZ120004': 'Mzuzu',
    'BL050022': 'Blantyre',
    'BT020011': 'Lilongwe',
}
_ALL_FACILITIES = ['LL040033', 'MZ120004', 'BL050022', 'BT020011']
_ALL_DISTRICTS  = ['Lilongwe', 'Mzuzu', 'Blantyre']

_FACILITY_COORDS = {
    'LL040033': (-13.9626, 33.7741, 'Lilongwe Central Hospital',  'Lilongwe'),
    'BT020011': (-13.9780, 33.7853, 'Bwaila District Hospital',   'Lilongwe'),
    'MZ120004': (-11.4534, 34.0192, 'Mzuzu Urban Health Centre',  'Mzuzu'),
    'BL050022': (-15.7861, 35.0058, 'Blantyre South Health Centre','Blantyre'),
}

_FACILITY_NAMES = {k: v[2] for k, v in _FACILITY_COORDS.items()}


# data helpers

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


# themed chart builders 

def _empty_card(title):
    return html.Div(className='mnid-chart-card', children=[
        html.Div(title, className='mnid-card-title'),
        html.Div('No data available', className='mnid-ind-note',
                 style={'padding': '24px 0', 'textAlign': 'center'}),
    ])


def _chart_card(title, fig):
    return html.Div(className='mnid-chart-card', children=[
        dcc.Graph(figure=fig, config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                  style={'height': '220px'}),
    ])


def _donut(counts_df, title, color_map=None):
    if not len(counts_df):
        return None
    palette = [OK_C, INFO_C, WARN_C, DANGER_C, '#7C3AED', '#0891B2', MUTED]
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
    palette = [OK_C, INFO_C, WARN_C, DANGER_C, '#7C3AED', '#0891B2', MUTED]
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


def _line(monthly_df, title, color=INFO_C, y_label='Clients'):
    if not len(monthly_df): return None
    r, g, b = int(color[1:3],16), int(color[3:5],16), int(color[5:7],16)
    fig = go.Figure(go.Scatter(
        x=monthly_df['month'], y=monthly_df['n'],
        mode='lines+markers',
        line=dict(color=color, width=2.5, shape='spline'),
        marker=dict(size=6, color=color, line=dict(color='#fff', width=1.5)),
        fill='tozeroy', fillcolor=f'rgba({r},{g},{b},0.07)',
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


# TREND SWITCHER

_CAT_LABELS = {'ANC': 'ANC', 'Labour': 'Labour & Delivery', 'Newborn': 'Newborn', 'PNC': 'PNC'}
_CAT_ORDER  = ['ANC', 'Labour', 'Newborn', 'PNC']


def _cat_trend_fig(df: pd.DataFrame, cat_inds: list, cat: str) -> go.Figure:
    palette = CAT_PALETTES.get(cat, [INFO_C])
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
        if has_data:
            fig.add_trace(go.Scatter(
                x=xs, y=ys, name=ind['label'],
                mode='lines+markers',
                line=dict(color=c, width=2.5, shape='spline'),
                marker=dict(size=6, color=c, line=dict(color='#fff', width=1.5)),
                fill='tozeroy', fillcolor=f'rgba({r},{g},{b},0.05)',
                connectgaps=True,
                hovertemplate=f'%{{x|%b %Y}}<br>{ind["label"]}: %{{y:.0f}}%<extra></extra>',
            ))
            non_none_xs = [x for x, y in zip(xs, ys) if y is not None]
            if len(non_none_xs) >= 2:
                fig.add_shape(type='line', x0=non_none_xs[0], x1=non_none_xs[-1],
                              y0=ind['target'], y1=ind['target'],
                              line=dict(color=c, width=1, dash='dot'), layer='below')
        else:
            fig.add_trace(go.Scatter(x=[], y=[], name=ind['label'],
                                     line=dict(color=c), showlegend=True))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        height=300,
        margin=dict(l=8, r=8, t=12, b=24),
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickformat='%b %y', tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED), range=[0, 105],
                   title=dict(text='Coverage %', font=dict(size=10, color=MUTED))),
        legend=dict(font=dict(size=10, color=DIM), bgcolor='rgba(0,0,0,0)',
                    orientation='v', x=1.01, y=1, xanchor='left', yanchor='top'),
        hovermode='x unified',
    )
    return fig


# Register clientside callback once at module level
clientside_callback(
    """
    function(n_clicks_list, stored_figs) {
        if (!stored_figs) return window.dash_clientside.no_update;
        var ctx = window.dash_clientside.callback_context;
        if (!ctx || !ctx.triggered || !ctx.triggered.length)
            return window.dash_clientside.no_update;
        var prop_id = ctx.triggered[0].prop_id;
        var id_part = prop_id.split('.')[0];
        try { var id_obj = JSON.parse(id_part); } catch(e) {
            return window.dash_clientside.no_update;
        }
        var cat = id_obj.index;
        if (!stored_figs[cat]) return window.dash_clientside.no_update;

        // Toggle active class on trend buttons (parse each element's actual Dash ID)
        document.querySelectorAll('[id*="trend-cat-btn"]').forEach(function(el) {
            try {
                var parsed = JSON.parse(el.id);
                if (parsed.index === cat) el.classList.add('active');
                else el.classList.remove('active');
            } catch(e) {}
        });

        return JSON.parse(stored_figs[cat]);
    }
    """,
    Output('mnid-trend-graph', 'figure'),
    Input({'type': 'trend-cat-btn', 'index': ALL}, 'n_clicks'),
    State('mnid-trend-store', 'data'),
    prevent_initial_call=True,
)


def _trend_switcher(df: pd.DataFrame, indicators: list) -> html.Div:
    tracked = [i for i in indicators if i.get('status') == 'tracked']
    stored_figs = {}
    for cat in _CAT_ORDER:
        cat_inds = [i for i in tracked if i.get('category') == cat]
        stored_figs[cat] = _cat_trend_fig(df, cat_inds, cat).to_json()  # handles datetime

    default_inds = [i for i in tracked if i.get('category') == 'ANC']
    default_fig  = _cat_trend_fig(df, default_inds, 'ANC')

    return html.Div(className='mnid-card', style={'marginBottom': '12px'}, children=[
        html.Div(style={'display': 'flex', 'alignItems': 'center',
                        'justifyContent': 'space-between', 'marginBottom': '8px'}, children=[
            html.Div('COVERAGE TREND', className='mnid-section-lbl',
                     style={'marginBottom': '0'}),
            html.Div(className='mnid-filter-row', children=[
                html.Button(
                    _CAT_LABELS.get(c, c),
                    id={'type': 'trend-cat-btn', 'index': c},
                    className='mnid-filter-btn' + (' active' if c == 'ANC' else ''),
                    n_clicks=0,
                )
                for c in _CAT_ORDER
            ]),
        ]),
        dcc.Store(id='mnid-trend-store', data=stored_figs),
        dcc.Graph(id='mnid-trend-graph', figure=default_fig,
                  config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}}, style={'height': '300px'}),
    ])


# HELPERS (vectorised coverage matrix, kept for potential future use)

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
    Vectorized: one groupby per indicator (not one filter per group × indicator).
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
    if pct >= 88:   return OK_C
    if pct >= 80:   return '#4ADE80'
    if pct >= 65:   return WARN_C
    if pct >= 40:   return '#FBBF24'
    return DANGER_C


# ── Vectorised facility coverage computation ───────────────────────────────

# ── Heatmap pre-computation ───────────────────────────────────────────────

def _compute_heatmap_store(mch_full: pd.DataFrame, tracked: list,
                           facility_code: str) -> dict:
    """Pre-compute all view × year matrices into a JSON-serialisable store."""
    current_district = _FACILITY_DISTRICT.get(facility_code, '')
    sorted_inds = []
    for cat in ['ANC', 'Labour', 'Newborn', 'PNC']:
        sorted_inds.extend(i for i in tracked if i.get('category') == cat)
    sorted_inds.extend(i for i in tracked if i not in sorted_inds)

    y_labels  = [i['label'][:32] for i in sorted_inds]
    y_targets = [i['target']     for i in sorted_inds]

    store = {
        'y_labels': y_labels, 'y_targets': y_targets,
        'current_fac': facility_code, 'current_district': current_district,
        'monthly': {}, 'by_facility': {}, 'by_district': {},
        'by_district_facs': {d: {} for d in _ALL_DISTRICTS},
        'yearly': {}, 'district_avgs': {},
    }

    if not len(mch_full) or not sorted_inds:
        return store

    year_options = {'All years': None, '2025': 2025, '2026': 2026}
    district_facs_map = {
        d: [f for f in _ALL_FACILITIES if _FACILITY_DISTRICT.get(f) == d]
        for d in _ALL_DISTRICTS
    }

    for ylbl, yval in year_options.items():
        df = mch_full[mch_full['Date'].dt.year == yval].copy() if yval else mch_full.copy()
        if not len(df):
            for key in ['monthly', 'by_facility', 'by_district']:
                store[key][ylbl] = {'x': [], 'z': [], 'tick_angle': 0}
            for d in _ALL_DISTRICTS:
                store['by_district_facs'][d][ylbl] = {'x': [], 'z': [], 'tick_angle': -30}
            store['district_avgs'][ylbl] = {d: None for d in _ALL_DISTRICTS}
            continue

        # Monthly — current facility only
        fac_df = df[df['Facility_CODE'] == facility_code]
        if len(fac_df):
            x_m, z_m = _matrix_monthly(fac_df, sorted_inds)
        else:
            x_m, z_m = [], []
        store['monthly'][ylbl] = {'x': x_m, 'z': z_m, 'tick_angle': 0}

        # Vectorised groupby for facility and district — one pass per indicator
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
        x_f = [f'{f}*' if f == facility_code else f for f in _ALL_FACILITIES]
        z_f = [[_cell(n_by_fac, d_by_fac, ind['id'], fac) for fac in _ALL_FACILITIES]
               for ind in sorted_inds]
        store['by_facility'][ylbl] = {
            'x': x_f, 'z': z_f, 'tick_angle': -30,
            'districts': [_FACILITY_DISTRICT.get(f, '') for f in _ALL_FACILITIES],
        }

        # All districts
        if has_dist:
            z_d = [[_cell(n_by_dist, d_by_dist, ind['id'], dist) for dist in _ALL_DISTRICTS]
                   for ind in sorted_inds]
            store['by_district'][ylbl] = {'x': _ALL_DISTRICTS[:], 'z': z_d, 'tick_angle': -20}
            d_avgs = {}
            for di, dist in enumerate(_ALL_DISTRICTS):
                vals = [z_d[ii][di] for ii in range(len(sorted_inds))
                        if ii < len(z_d) and di < len(z_d[ii]) and z_d[ii][di] is not None]
                d_avgs[dist] = round(sum(vals) / len(vals), 1) if vals else None
            store['district_avgs'][ylbl] = d_avgs
        else:
            store['by_district'][ylbl]   = {'x': [], 'z': [], 'tick_angle': -20}
            store['district_avgs'][ylbl] = {d: None for d in _ALL_DISTRICTS}

        # Per-district facility breakdowns
        for dist in _ALL_DISTRICTS:
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

    # ── Encounter volume counts (for right-panel stats) ─────────────────────
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


# ── Heatmap figure builder ─────────────────────────────────────────────────

def _build_heatmap_fig(stored: dict, view: str, year: str,
                       district: str | None = None,
                       sel_inds: list | None = None) -> go.Figure:
    all_labels  = stored.get('y_labels', [])
    all_targets = stored.get('y_targets', [])

    # Filter rows to selected indicators (if any selection is active)
    if sel_inds:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in sel_inds]
    else:
        rows_idx = list(range(len(all_labels)))

    y_labels  = [all_labels[i] for i in rows_idx]
    y_targets = [all_targets[i] for i in rows_idx]
    n_inds    = len(y_labels)
    height    = max(n_inds * 30 + 150, 380)

    if view == 'monthly':
        data = stored.get('monthly', {}).get(year, {})
    elif view == 'by_facility':
        data = stored.get('by_facility', {}).get(year, {})
    elif view == 'by_district':
        data = stored.get('by_district', {}).get(year, {})
    elif view == 'district_facs':
        dist = district or stored.get('current_district', _ALL_DISTRICTS[0])
        data = stored.get('by_district_facs', {}).get(dist, {}).get(year, {})
    elif view == 'yearly':
        data = stored.get('yearly') or {}
    else:
        data = {}

    x_labels   = data.get('x', [])
    z_raw      = data.get('z', [])
    z          = [z_raw[i] for i in rows_idx if i < len(z_raw)]
    tick_angle = data.get('tick_angle', 0)

    if view in ('by_district', 'by_facility', 'district_facs'):
        return _build_geo_heatmap_fig(stored, view, year, district, sel_inds)

    if not x_labels or not z:
        fig = go.Figure()
        fig.add_annotation(text='No data for this selection',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=GRID_C,
                          height=height, margin=dict(l=220, r=80, t=16, b=60))
        return fig

    _customdata = None
    if y_targets and all(t is not None for t in y_targets):
        _customdata = [[tgt] * len(x_labels) for tgt, _ in zip(y_targets, z)]
    _hover = '<b>%{y}</b><br>%{x}: <b>%{z:.0f}%</b><extra></extra>'
    if _customdata is not None:
        _hover = ('<b>%{y}</b><br>%{x}: <b>%{z:.0f}%</b>'
                  '<br>Target: %{customdata[0]}%<extra></extra>')
    fig = go.Figure(go.Heatmap(
        z=z, x=x_labels, y=y_labels,
        colorscale=HEATMAP_CS,
        zmin=0, zmax=100,
        zsmooth=False,
        hoverongaps=False,
        customdata=_customdata,
        colorbar=dict(
            thickness=14,
            title=dict(text='Coverage %', side='right',
                       font=dict(size=9, color=DIM)),
            tickfont=dict(size=9, color=DIM),
            tickvals=[0, 40, 65, 80, 88, 100],
            ticktext=['0%', '40%', '65%', '80%', '88%', '100%'],
            len=0.85,
        ),
        hovertemplate=_hover,
        ygap=1.5, xgap=1.5,
    ))

    # Cell value annotations for small heatmaps
    annotations = []
    if len(x_labels) <= 8:
        for ii, row in enumerate(z):
            for jj, val in enumerate(row):
                if val is not None:
                    txt_col = '#fff' if val < 65 else '#222'
                    annotations.append(dict(
                        x=x_labels[jj], y=y_labels[ii],
                        text=f'{val:.0f}%',
                        showarrow=False,
                        font=dict(size=9, color=txt_col, family=FONT),
                    ))

    # Target reference: annotate indicator labels with target info
    y_annots = []
    for ii, (lbl, tgt) in enumerate(zip(y_labels, y_targets)):
        on_tgt_count = sum(1 for row in ([z[ii]] if ii < len(z) else [[]])
                           for v in row if v is not None and v >= tgt)
        marker = ' ✓' if on_tgt_count > 0 else ''
        y_annots.append(dict(
            x=-0.001, y=lbl,
            xref='paper', yref='y',
            text=f'<span style="color:{MUTED}; font-size:8px">▶{tgt}%</span>',
            showarrow=False, xanchor='right',
            font=dict(size=7, color=MUTED, family=FONT),
        ))

    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        height=height,
        margin=dict(l=230, r=90, t=16, b=70),
        xaxis=dict(tickangle=tick_angle, tickfont=dict(size=10, color=DIM),
                   showgrid=False, side='bottom'),
        yaxis=dict(tickfont=dict(size=10, color=DIM),
                   showgrid=False, autorange='reversed'),
        annotations=annotations + y_annots,
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
    )
    return fig


# ── Geographic map data for main heatmap ───────────────────────────────────

_DISTRICT_POLYGONS = {
    'Mzuzu': [
        (4.8, 99.0), (4.2, 95.5), (4.6, 92.0), (3.9, 87.5), (4.5, 82.0),
        (5.1, 78.0), (6.1, 74.0), (7.0, 70.0), (7.5, 66.0), (8.0, 62.0),
        (8.7, 58.0), (9.1, 54.0), (8.7, 51.0), (7.6, 50.0), (6.7, 51.5),
        (5.7, 53.5), (5.0, 56.0), (4.6, 60.0), (4.2, 65.0), (3.8, 71.0),
        (3.7, 77.0), (3.9, 84.0), (4.2, 90.0), (4.6, 95.0),
    ],
    'Lilongwe': [
        (4.6, 60.0), (5.0, 56.0), (5.7, 53.5), (6.7, 51.5), (7.6, 50.0),
        (8.7, 51.0), (9.4, 48.0), (10.0, 44.0), (10.4, 40.0), (10.8, 36.0),
        (10.9, 32.0), (10.6, 28.0), (9.8, 25.0), (9.0, 23.0), (8.1, 22.0),
        (7.3, 23.0), (6.6, 24.5), (5.9, 26.5), (5.3, 30.0), (4.7, 34.0),
        (4.1, 38.0), (3.8, 43.0), (3.8, 48.0), (4.1, 54.0),
    ],
    'Blantyre': [
        (5.3, 30.0), (5.9, 26.5), (6.6, 24.5), (7.3, 23.0), (8.1, 22.0),
        (9.0, 23.0), (9.8, 25.0), (10.6, 28.0), (11.3, 24.0), (11.7, 20.0),
        (11.6, 16.0), (11.1, 12.0), (10.6, 9.0), (10.0, 6.0), (9.5, 3.5),
        (8.7, 1.2), (7.5, 0.5), (6.5, 1.6), (5.7, 3.8), (5.1, 7.0),
        (4.9, 11.0), (4.8, 16.0), (4.9, 21.0), (5.0, 25.0),
    ],
}

_DISTRICT_LABEL_POS = {
    'Mzuzu': (6.0, 75.0),
    'Lilongwe': (7.1, 40.0),
    'Blantyre': (7.7, 11.0),
}

_FACILITY_MAP_POS = {
    'MZ120004': (6.1, 77.5),
    'LL040033': (7.2, 42.5),
    'BT020011': (6.4, 36.2),
    'BL050022': (8.1, 12.3),
}


def _build_geo_heatmap_fig(stored: dict, view: str, year: str,
                           district: str | None = None,
                           sel_inds: list | None = None) -> go.Figure:
    district_avgs = stored.get('district_avgs', {}).get(year, {})
    current_fac   = stored.get('current_fac', '')
    current_dist  = stored.get('current_district', '')
    all_labels    = stored.get('y_labels', [])

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

    focus_dist = district or current_dist
    highlighted = {focus_dist} if view == 'district_facs' else set(_ALL_DISTRICTS)

    fig = go.Figure()
    for dist in _ALL_DISTRICTS:
        pts = _DISTRICT_POLYGONS.get(dist, [])
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cov = district_avgs.get(dist)
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode='lines',
            fill='toself',
            fillcolor=_cov_color(cov) if cov is not None else '#D6D3CB',
            line=dict(color=INFO_C if dist in highlighted else '#FFFFFF',
                      width=3 if dist in highlighted else 1.6),
            opacity=1.0 if dist in highlighted else 0.28,
            customdata=[[dist, cov]] * len(xs),
            hovertemplate='<b>%{customdata[0]}</b><br>Avg coverage: %{customdata[1]:.1f}%<extra></extra>' if cov is not None
                          else '<b>%{customdata[0]}</b><br>No data<extra></extra>',
            showlegend=False,
        ))

    label_x = []
    label_y = []
    label_text = []
    for dist in _ALL_DISTRICTS:
        if view == 'district_facs' and dist != focus_dist:
            continue
        pos = _DISTRICT_LABEL_POS.get(dist)
        if not pos:
            continue
        cov = district_avgs.get(dist)
        label_x.append(pos[0])
        label_y.append(pos[1])
        label_text.append(f'<b>{dist}</b><br>{cov:.0f}%' if cov is not None else f'<b>{dist}</b><br>No data')
    if label_x:
        fig.add_trace(go.Scatter(
            x=label_x,
            y=label_y,
            mode='text',
            text=label_text,
            textfont=dict(size=16, color='white', family=FONT),
            hoverinfo='skip',
            showlegend=False,
        ))

    if view in ('by_facility', 'district_facs'):
        fac_codes = _ALL_FACILITIES if view == 'by_facility' else [
            f for f in _ALL_FACILITIES if _FACILITY_DISTRICT.get(f) == focus_dist
        ]
        label_pos_map = {
            'MZ120004': 'middle right',
            'LL040033': 'top right',
            'BT020011': 'bottom right',
            'BL050022': 'middle right',
        }
        for fac in fac_codes:
            pos = _FACILITY_MAP_POS.get(fac)
            if not pos:
                continue
            avg = _fac_avg(fac)
            fig.add_trace(go.Scatter(
                x=[pos[0]],
                y=[pos[1]],
                mode='markers+text',
                marker=dict(
                    size=16 if fac == current_fac else 12,
                    color=_cov_color(avg) if avg is not None else '#FFFFFF',
                    line=dict(color=INFO_C if fac == current_fac else '#FFFFFF',
                              width=2 if fac == current_fac else 1.3),
                    symbol='square',
                ),
                text=[_FACILITY_NAMES.get(fac, fac)],
                textposition=label_pos_map.get(fac, 'top right'),
                textfont=dict(size=10, color=TEXT, family=FONT),
                hovertemplate=f'<b>{_FACILITY_NAMES.get(fac, fac)}</b><br>{avg:.0f}%<extra></extra>' if avg is not None
                              else f'<b>{_FACILITY_NAMES.get(fac, fac)}</b><br>No data<extra></extra>',
                showlegend=False,
            ))

    title = 'District Coverage Map' if view == 'by_district' else (
        'Facility Coverage Map' if view == 'by_facility' else f'{focus_dist} Facility Coverage Map'
    )
    fig.update_layout(
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        height=620,
        margin=dict(l=20, r=20, t=48, b=20),
        font=dict(family=FONT),
        xaxis=dict(visible=False, range=[1.8, 13.6], fixedrange=True),
        yaxis=dict(visible=False, range=[-2, 101], fixedrange=True),
        annotations=[dict(
            x=0.01, y=1.03, xref='paper', yref='paper',
            text=title, showarrow=False, xanchor='left',
            font=dict(size=15, color=TEXT, family=FONT),
        )],
    )
    fig.update_yaxes(scaleanchor='x', scaleratio=0.16)
    return fig


# ── Right panel: stylised Malawi shape + indicator stats ──────────────────

def _build_district_treemap(stored: dict, view: str, year: str,
                             district: str | None = None,
                             sel_inds: list | None = None) -> go.Figure:
    """Treemap of districts/facilities colored by avg indicator coverage — looks like the screenshot."""
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

    geo_w = {'Mzuzu': 26, 'Lilongwe': 43, 'Blantyre': 31}

    if view in ('by_district', 'monthly', 'yearly'):
        labels  = list(_ALL_DISTRICTS)
        parents = [''] * len(labels)
        values  = [float(geo_w.get(d, 33)) for d in labels]
        covs    = [district_avgs.get(d) for d in labels]
        hl_set  = {current_dist} if view in ('monthly', 'yearly') else set(labels)

    elif view == 'by_facility':
        dist_labels = list(_ALL_DISTRICTS)
        fac_labels  = [f'{f}*' if f == current_fac else f for f in _ALL_FACILITIES]
        labels  = dist_labels + fac_labels
        parents = [''] * len(dist_labels) + [_FACILITY_DISTRICT.get(f, '') for f in _ALL_FACILITIES]
        d_covs  = [district_avgs.get(d) for d in dist_labels]
        f_covs  = [_fac_avg(f) for f in _ALL_FACILITIES]
        covs    = d_covs + f_covs
        values  = [float(geo_w.get(d, 33)) for d in dist_labels] + [1.0] * len(_ALL_FACILITIES)
        hl_set  = set(labels)

    elif view == 'district_facs':
        dist_filter = district or current_dist
        facs = [f for f in _ALL_FACILITIES if _FACILITY_DISTRICT.get(f) == dist_filter]
        labels  = [f'{f}*' if f == current_fac else f for f in facs]
        parents = [''] * len(labels)
        values  = [1.0] * len(labels)
        covs    = [_fac_avg(f) for f in facs]
        hl_set  = set(labels)

    else:
        labels, parents, values, covs, hl_set = [], [], [], [], set()

    texts  = [f'{c:.0f}%' if c is not None else 'No data' for c in covs]
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
        textfont=dict(size=11, color='white', family=FONT),
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
    else:
        highlight = None

    treemap_fig  = _build_district_treemap(stored, view, year, district, sel_inds)
    malawi_panel = dcc.Graph(
        figure=treemap_fig,
        config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
        style={'marginBottom': '6px'},
    )

    # Stats from selected view data
    if view == 'monthly':
        data = stored.get('monthly', {}).get(year, {})
        view_title = 'This facility — monthly'
    elif view == 'by_facility':
        data = stored.get('by_facility', {}).get(year, {})
        view_title = 'All facilities'
    elif view == 'by_district':
        data = stored.get('by_district', {}).get(year, {})
        view_title = 'All districts'
    elif view == 'district_facs':
        dist = district or current_district
        data = stored.get('by_district_facs', {}).get(dist, {}).get(year, {})
        view_title = f'{dist} — district facilities'
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
                                    'background': col, 'borderRadius': '1px'}),
                ]),
            ]),
            html.Div(style={'textAlign': 'right', 'flexShrink': '0'}, children=[
                html.Span(f'{s["avg"]:.0f}%',
                          style={'fontSize': '10px', 'fontWeight': '600', 'color': col}),
                html.Span(' ✓' if s['on_target'] else '',
                          style={'fontSize': '9px', 'color': OK_C}),
            ]),
        ]))

    # Colour legend
    legend_items = [
        (OK_C, '≥88%'), ('#C0DD97', '80-87%'),
        (WARN_C, '65-79%'), ('#E8A830', '40-64%'), (DANGER_C, '<40%'),
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
            html.Span(f'{overall_avg:.0f}%' if overall_avg is not None else '—',
                      style={'fontSize': '18px', 'fontWeight': '700',
                             'color': _cov_color(overall_avg)}),
        ]),
        html.Div(f'{on_tgt}/{len(ind_stats)} indicators on target',
                 style={'fontSize': '10px', 'color': MUTED, 'marginBottom': '8px'}),
        html.Div('INDICATOR BREAKDOWN', className='mnid-section-lbl'),
        html.Div(style={'overflowY': 'auto', 'maxHeight': '220px'}, children=ind_rows),
    ]


# ── Scroll-spy: highlight active sidebar link ─────────────────────────────
# Runs once on load via clientside_callback listening to a URL interval tick.
# Uses IntersectionObserver to mark .mnid-sidebar-link as active.

clientside_callback(
    """
    function(n) {
        if (window._mnidScrollSpyActive) return '';
        window._mnidScrollSpyActive = true;

        var sectionIds = ['mnid-summary','mnid-coverage','mnid-trends',
                          'mnid-heatmap','mnid-analysis','mnid-comparative','mnid-readiness'];

        function setActive(id) {
            sectionIds.forEach(function(sid) {
                var a = document.querySelector('.mnid-sidebar-link[href="#' + sid + '"]');
                if (!a) return;
                if (sid === id) a.classList.add('active');
                else a.classList.remove('active');
            });
        }

        function updateActive() {
            var threshold = 140;
            var activeId = sectionIds[0];
            for (var i = 0; i < sectionIds.length; i++) {
                var el = document.getElementById(sectionIds[i]);
                if (el && el.getBoundingClientRect().top <= threshold) {
                    activeId = sectionIds[i];
                }
            }
            setActive(activeId);
        }

        window.addEventListener('scroll', updateActive, { passive: true });
        // Also re-check after a short delay to catch initial render
        setTimeout(updateActive, 200);
        updateActive();
        return '';
    }
    """,
    Output('mnid-scrollspy-out', 'data'),
    Input('mnid-scrollspy-tick', 'n_intervals'),
    prevent_initial_call=False,
)

# ── Module-level callback ──────────────────────────────────────────────────

@callback(
    Output('mnid-heatmap-graph', 'figure'),
    Output('mnid-heatmap-right', 'children'),
    Input('mnid-heatmap-view',       'value'),
    Input('mnid-heatmap-year',       'value'),
    Input('mnid-heatmap-district',   'value'),
    Input('mnid-heatmap-indicators', 'value'),
    State('mnid-heatmap-store',      'data'),
    prevent_initial_call=True,
)
def update_heatmap_view(view, year, district, sel_inds, stored):
    if not stored:
        return go.Figure(), []
    v = view or 'monthly'
    y = year or 'All years'
    fig   = _build_heatmap_fig(stored, v, y, district, sel_inds)
    panel = _build_malawi_panel(stored, v, y, district, sel_inds)
    return fig, panel


@callback(
    Output('mnid-compare-fac-pie-a', 'figure'),
    Output('mnid-compare-fac-pie-b', 'figure'),
    Output('mnid-compare-dist-pie-a', 'figure'),
    Output('mnid-compare-dist-pie-b', 'figure'),
    Input('mnid-compare-fac-a', 'value'),
    Input('mnid-compare-fac-b', 'value'),
    Input('mnid-compare-dist-a', 'value'),
    Input('mnid-compare-dist-b', 'value'),
    Input('mnid-compare-viz-type', 'value'),
    State('mnid-compare-store', 'data'),
)
def update_compare_charts(fac_a, fac_b, dist_a, dist_b, viz_type, stored_inds):
    viz_type = viz_type or 'pie'
    try:
        df_all   = pd.read_parquet('data/latest_data_opd.parquet')
        mch_full = df_all[df_all['Program'].str.contains(
            'Maternal|Neonatal', case=False, na=False)].copy()
    except Exception:
        mch_full = pd.DataFrame()

    tracked = stored_inds or []

    _empty_counts = {'On target': 0, 'Below target': 0, 'No data': 0}

    def _build(title, df):
        if viz_type == 'bar':
            counts = _compare_status_counts(df, tracked) if (len(df) and tracked) else _empty_counts
            return _build_compare_bar(title, counts)
        elif viz_type == 'heatmap':
            return _build_compare_heatmap(title, df, tracked)
        else:  # pie (default)
            counts = _compare_status_counts(df, tracked) if (len(df) and tracked) else _empty_counts
            return _build_compare_pie(title, counts)

    fac_a  = fac_a  or _ALL_FACILITIES[0]
    fac_b  = fac_b  or (_ALL_FACILITIES[1] if len(_ALL_FACILITIES) > 1 else _ALL_FACILITIES[0])
    dist_a = dist_a or _ALL_DISTRICTS[0]
    dist_b = dist_b or (_ALL_DISTRICTS[1] if len(_ALL_DISTRICTS) > 1 else _ALL_DISTRICTS[0])

    fac_a_df  = mch_full[mch_full['Facility_CODE'] == fac_a]  if len(mch_full) else pd.DataFrame()
    fac_b_df  = mch_full[mch_full['Facility_CODE'] == fac_b]  if len(mch_full) else pd.DataFrame()
    dist_a_df = mch_full[mch_full['District'] == dist_a] if (len(mch_full) and 'District' in mch_full.columns) else pd.DataFrame()
    dist_b_df = mch_full[mch_full['District'] == dist_b] if (len(mch_full) and 'District' in mch_full.columns) else pd.DataFrame()

    return (
        _build(f'Facility — {_FACILITY_NAMES.get(fac_a, fac_a)}',  fac_a_df),
        _build(f'Facility — {_FACILITY_NAMES.get(fac_b, fac_b)}',  fac_b_df),
        _build(f'District — {dist_a}', dist_a_df),
        _build(f'District — {dist_b}', dist_b_df),
    )


# ── Main heatmap section layout ────────────────────────────────────────────

def _coverage_heatmap_section(indicators: list, facility_code: str) -> html.Div:
    """Multi-view indicator heatmap with Malawi district panel and live filters."""
    try:
        df_all   = pd.read_parquet('data/latest_data_opd.parquet')
        mch_full = df_all[df_all['Program'].str.contains(
            'Maternal|Neonatal', case=False, na=False)].copy()
        if 'Date' in mch_full.columns:
            mch_full['Date'] = pd.to_datetime(mch_full['Date'], errors='coerce')
    except Exception:
        mch_full = pd.DataFrame()

    tracked = [i for i in indicators if i.get('status') == 'tracked']
    store   = _compute_heatmap_store(mch_full, tracked, facility_code)

    initial_fig   = _build_heatmap_fig(store, 'monthly', 'All years')
    initial_panel = _build_malawi_panel(store, 'monthly', 'All years')

    cur_dist   = store.get('current_district', _ALL_DISTRICTS[0])
    has_yearly = bool(store.get('yearly', {}).get('x'))
    all_labels = store.get('y_labels', [])

    view_options = [
        {'label': 'This Facility — Monthly',  'value': 'monthly'},
        {'label': 'My District Facilities',   'value': 'district_facs'},
        {'label': 'All Districts',            'value': 'by_district'},
        {'label': 'All Facilities',           'value': 'by_facility'},
    ]
    if has_yearly:
        view_options.append({'label': 'Year-over-Year', 'value': 'yearly'})

    year_opts     = [{'label': y, 'value': y} for y in ['All years', '2025', '2026']]
    district_opts = [{'label': d, 'value': d} for d in _ALL_DISTRICTS]
    ind_opts      = [{'label': lbl, 'value': lbl} for lbl in all_labels]

    _dd_style = {'fontSize': '12px', 'minWidth': '0'}
    _lbl_style = {'fontSize': '10px', 'color': MUTED, 'fontWeight': '600',
                  'marginBottom': '3px'}

    return html.Div(id='mnid-heatmap-inner', className='mnid-card',
                    style={'marginBottom': '12px'}, children=[
        dcc.Store(id='mnid-heatmap-store', data=store),

        html.Div('INDICATOR COVERAGE HEATMAP', className='mnid-section-lbl'),

        # ── Filter bar ────────────────────────────────────────────────────
        html.Div(style={
            'display': 'grid',
            'gridTemplateColumns': '2fr 1.1fr 1.1fr 1.3fr',
            'gap': '10px', 'alignItems': 'end',
            'marginBottom': '12px',
        }, children=[
            # View selector
            html.Div(children=[
                html.Div('View', style=_lbl_style),
                dcc.Dropdown(
                    id='mnid-heatmap-view',
                    options=view_options,
                    value='monthly',
                    clearable=False,
                    style=_dd_style,
                ),
            ]),
            # Year filter
            html.Div(children=[
                html.Div('Year', style=_lbl_style),
                dcc.Dropdown(
                    id='mnid-heatmap-year',
                    options=year_opts,
                    value='All years',
                    clearable=False,
                    style=_dd_style,
                ),
            ]),
            # District filter
            html.Div(children=[
                html.Div('District', style=_lbl_style),
                dcc.Dropdown(
                    id='mnid-heatmap-district',
                    options=district_opts,
                    value=cur_dist,
                    clearable=False,
                    style=_dd_style,
                ),
            ]),
            # Indicator multi-select
            html.Div(children=[
                html.Div('Indicators', style=_lbl_style),
                dcc.Dropdown(
                    id='mnid-heatmap-indicators',
                    options=ind_opts,
                    value=all_labels,   # all selected by default
                    multi=True,
                    placeholder='Select indicators…',
                    style=_dd_style,
                ),
            ]),
        ]),

        # ── Main content: heatmap + Malawi panel ──────────────────────────
        html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 230px',
                        'gap': '12px', 'alignItems': 'start'}, children=[
            dcc.Graph(
                id='mnid-heatmap-graph', figure=initial_fig,
                config={'displayModeBar': True,
                        'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                        'scrollZoom': True},
            ),
            html.Div(
                id='mnid-heatmap-right',
                style={'padding': '12px', 'background': '#FAFAF8',
                       'border': f'0.5px solid {BORDER}', 'borderRadius': '10px',
                       'maxHeight': '680px', 'overflowY': 'auto'},
                children=initial_panel,
            ),
        ]),

        # ── Key ───────────────────────────────────────────────────────────
        html.P(
            'Green ≥ 88% on target  ·  Amber 65–79% performing  ·  '
            'Red < 65% needs review  ·  Grey = no data  ·  * = current facility',
            style={'fontSize': '9px', 'color': MUTED, 'marginTop': '6px'},
        ),
    ])

# indicator cards

def _ind_card(ind: dict, df: pd.DataFrame) -> html.Div:
    if ind.get('status') == 'awaiting_baseline':
        return html.Div(className='mnid-ind-card awaiting', children=[
            html.Div(ind['label'], className='mnid-ind-label'),
            html.Div([
                html.Span('—', className='mnid-ind-pct info'),
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
            html.Span(f'{pct:.0f}%', className=f'mnid-ind-pct {cls}'),
            badge,
        ], className='mnid-ind-top'),
        html.Div(f'{num} / {den}  ·  Target {target}%', className='mnid-ind-sub'),
    ])


# ── Phase gauge donuts ────────────────────────────────────────────────────

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
            text=f'<b>{avg_pct:.0f}%</b>',
            x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False,
            font=dict(size=20, color=color, family=FONT),
        )],
    )
    return fig


def _phase_gauge_row(by_cat: dict, df: pd.DataFrame) -> html.Div:
    """Row of 4 mini donut gauges — one per care phase."""
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


# ── Key clinical outcomes (4 donuts always visible) ───────────────────────

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


# ── Coverage phase bar chart ───────────────────────────────────────────────

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
            html.Div('—', style={
                'fontSize': '32px', 'color': MUTED, 'lineHeight': '1',
            }),
            html.Div(message, style={
                'fontSize': '13px', 'color': DIM, 'fontFamily': FONT,
                'textAlign': 'center',
            }),
        ]),
    ])


def _coverage_charts_section(by_cat: dict, df: pd.DataFrame) -> html.Div:
    """2-column grid of per-phase coverage bar charts (replaces accordion cards)."""
    phases = [
        ('ANC',     'Antenatal Care (ANC)'),
        ('Labour',  'Labour & Delivery'),
        ('Newborn', 'Newborn Care'),
        ('PNC',     'Postnatal Care (PNC)'),
    ]
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

        pills = [html.Span(f'{len(tracked)} tracked', className='mnid-pill mnid-pill-green')]
        if awaiting:
            pills.append(html.Span(f'{len(awaiting)} awaiting', className='mnid-pill mnid-pill-amber'))
        if avg_pct is not None:
            pc = 'mnid-pill-green' if avg_pct >= 80 else ('mnid-pill-amber' if avg_pct >= 65 else 'mnid-pill-red')
            pills.append(html.Span(f'Avg {avg_pct:.0f}%', className=f'mnid-pill {pc}'))

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
            html.P('▏= target', style={'fontSize': '9px', 'color': MUTED,
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

    pills = [html.Span(f'{len(tracked)} tracked', className='mnid-pill mnid-pill-green')]
    if awaiting:
        pills.append(html.Span(f'{len(awaiting)} awaiting',
                               className='mnid-pill mnid-pill-amber'))
    if avg_pct is not None:
        pc = 'mnid-pill-green' if avg_pct >= 80 else ('mnid-pill-amber' if avg_pct >= 65
                                                        else 'mnid-pill-red')
        pills.append(html.Span(f'Avg {avg_pct:.0f}%', className=f'mnid-pill {pc}'))

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

    fig = _line(monthly, 'ANC Visits Over Time', color=INFO_C, y_label='Unique Clients')
    if fig: charts.append(_chart_card('', fig))

    for concept, title in [
        ('Anemia screening',            'Anaemia Screening'),
        ('Infection screening',         'Infection Screening'),
        ('High blood pressure screening','Blood Pressure Screening'),
    ]:
        vc = _value_counts(df, concept)
        fig = _donut(vc, title, color_map={
            'Screened': OK_C, 'Not screened': GRID_C,
        })
        if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'POCUS completed')
    fig = _donut(vc, 'POCUS Completed', color_map={'Yes': OK_C, 'No': GRID_C})
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'HIV Test')
    fig = _donut(vc, 'HIV Testing Status', color_map={
        'Non-reactive': OK_C, 'Reactive': DANGER_C,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Number of tetanus doses', col='Value')
    fig = _hbar(vc, 'Tetanus Dose Distribution')
    if fig: charts.append(_chart_card('', fig))

    return charts


def _labour_charts(df):
    charts = []
    monthly = _monthly_visits(df, 'LABOUR AND DELIVERY')
    fig = _line(monthly, 'Labour & Delivery Visits', color=WARN_C, y_label='Clients')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Place of delivery')
    fig = _donut(vc, 'Place of Delivery', color_map={
        'This facility': OK_C, 'this facility': OK_C,
        'Home': DANGER_C, 'Referral facility': WARN_C, 'In transit': '#92400E',
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
        'Live births': OK_C,
        'Fresh stillbirth': DANGER_C,
        'Macerated stillbirth': '#92400E',
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
            'Yes': OK_C, 'Used': OK_C, 'Completed': OK_C,
            'No': DANGER_C, 'Not used': DANGER_C, 'Not required': MUTED,
            'Partial': WARN_C, 'Not eligible': MUTED,
        })
        if fig: charts.append(_chart_card('', fig))

    return charts


def _pnc_charts(df):
    charts = []
    monthly = _monthly_visits(df, 'POSTNATAL CARE')
    fig = _line(monthly, 'PNC Visits Over Time', color='#7C3AED', y_label='Clients')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Postnatal check period')
    fig = _hbar(vc, 'PNC Visit Timing')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Breast feeding')
    fig = _donut(vc, 'Breastfeeding Mode', color_map={
        'Exclusive': OK_C, 'exclusive breastfeeding': OK_C,
        'Mixed': WARN_C, 'Not breastfeeding': DANGER_C,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Status of the mother')
    fig = _donut(vc, 'Mother Final Status', color_map={
        'Stable': OK_C, 'Death': DANGER_C, 'Referred': WARN_C,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Status of baby')
    fig = _donut(vc, 'Baby Final Status', color_map={
        'Stable': OK_C, 'Died': DANGER_C, 'Referred': WARN_C,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Postnatal complications')
    fig = _hbar(vc, 'Postnatal Complications')
    if fig: charts.append(_chart_card('', fig))

    return charts


def _newborn_charts(df):
    charts = []
    monthly = _monthly_visits(df, 'NEONATAL CARE')
    fig = _line(monthly, 'Neonatal Care Admissions', color=OK_C, y_label='Babies')
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Thermal status on admission')
    fig = _donut(vc, 'Thermal Status on Admission', color_map={
        'Not hypothermic': OK_C,
        'Mild hypothermia': WARN_C,
        'Moderate hypothermia': DANGER_C,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Neonatal resuscitation provided')
    fig = _donut(vc, 'Neonatal Resuscitation', color_map={
        'Yes': OK_C, 'Stimulation only': INFO_C,
        'Bag and mask': WARN_C, 'No': DANGER_C, 'Not required': MUTED,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'iKMC initiated')
    fig = _donut(vc, 'iKMC Initiated', color_map={
        'Yes': OK_C, 'No': DANGER_C, 'Not eligible': MUTED,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'CPAP support')
    fig = _donut(vc, 'CPAP Support Type', color_map={
        'Bubble CPAP': OK_C, 'Nasal oxygen': INFO_C, 'None': MUTED,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Phototherapy given')
    fig = _donut(vc, 'Phototherapy Given', color_map={
        'Yes': OK_C, 'No': DANGER_C,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Parenteral antibiotics given')
    fig = _donut(vc, 'Parenteral Antibiotics', color_map={
        'Yes': OK_C, 'No': DANGER_C,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Newborn baby complications')
    fig = _hbar(vc, 'Newborn Complications')
    if fig: charts.append(_chart_card('', fig))

    return charts


# system readiness

def _stat_row(label, num, den, pct, tgt=None):
    cls = _css(pct, tgt) if tgt else 'info'
    return html.Div(className='mnid-stat-row', children=[
        html.Span(label, className='mnid-stat-lbl'),
        html.Div(style={'display':'flex','gap':'8px','alignItems':'center'}, children=[
            html.Span(f'{num}/{den}', style={'fontSize':'11px','color':MUTED}),
            html.Span(f'{pct:.0f}%', className='mnid-stat-val'),
            html.Span('●', style={'color': _CLR[cls], 'fontSize':'10px'}),
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
    colors = [OK_C, WARN_C, '#D6D3CB']

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
    colors = [OK_C, WARN_C, '#D6D3CB']

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
    for ind in tracked:
        label = ind.get('label', ind.get('id', '?'))
        if df.empty:
            pct = 0.0
        else:
            _, _, pct = _cov(df, ind['numerator_filters'], ind['denominator_filters'])
        target = ind.get('target', 0)
        names.append(label[:38])
        pcts.append(pct)
        if pct == 0:
            colors_list.append('#E5E7EB')
        elif pct >= target:
            colors_list.append(OK_C)
        elif pct >= target * 0.75:
            colors_list.append(WARN_C)
        else:
            colors_list.append(DANGER_C)

    if not names:
        fig = go.Figure()
        fig.update_layout(**_CHART_LAYOUT, height=260)
        return fig

    fig = go.Figure(go.Bar(
        x=pcts,
        y=names,
        orientation='h',
        marker=dict(color=colors_list, line=dict(color='#fff', width=0.5)),
        text=[f'{p:.0f}%' for p in pcts],
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

def _comparative_analysis_section(indicators: list, facility_code: str) -> html.Div:
    """Side-by-side coverage comparison across facilities and districts."""
    tracked = [i for i in indicators if i.get('status') == 'tracked']
    fac_opts = [{'label': _FACILITY_NAMES.get(f, f), 'value': f} for f in _ALL_FACILITIES]
    dist_opts = [{'label': d, 'value': d} for d in _ALL_DISTRICTS]
    compare_selector = html.Div(className='mnid-chart-card mnid-compare-card', children=[
        html.Div(style={'display': 'flex', 'alignItems': 'center',
                        'justifyContent': 'space-between', 'marginBottom': '10px'}, children=[
            html.Div('SELECT COMPARISONS', className='mnid-card-title',
                     style={'marginBottom': '0'}),
            html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'}, children=[
                html.Span('Chart type:', style={'fontSize': '11px', 'color': DIM,
                                                'fontWeight': '600', 'letterSpacing': '0.04em'}),
                dcc.RadioItems(
                    id='mnid-compare-viz-type',
                    options=[
                        {'label': 'Pie',     'value': 'pie'},
                        {'label': 'Bar',     'value': 'bar'},
                        {'label': 'Heatmap', 'value': 'heatmap'},
                    ],
                    value='pie',
                    inline=True,
                    inputStyle={'marginRight': '4px'},
                    labelStyle={'marginRight': '12px', 'fontSize': '12px',
                                'color': TEXT, 'cursor': 'pointer'},
                ),
            ]),
        ]),
        html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                        'gap': '12px', 'alignItems': 'start'}, children=[
            html.Div(children=[
                html.Div('Facilities vs Facilities', className='mnid-ind-sub'),
                html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                                'gap': '8px'}, children=[
                    dcc.Dropdown(
                        id='mnid-compare-fac-a',
                        options=fac_opts,
                        value=_ALL_FACILITIES[0] if _ALL_FACILITIES else None,
                        clearable=False,
                    ),
                    dcc.Dropdown(
                        id='mnid-compare-fac-b',
                        options=fac_opts,
                        value=_ALL_FACILITIES[1] if len(_ALL_FACILITIES) > 1 else (_ALL_FACILITIES[0] if _ALL_FACILITIES else None),
                        clearable=False,
                    ),
                ]),
                html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                                'gap': '8px', 'marginTop': '6px'}, children=[
                    dcc.Graph(id='mnid-compare-fac-pie-a',
                              config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                              style={'height': '300px'}),
                    dcc.Graph(id='mnid-compare-fac-pie-b',
                              config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                              style={'height': '300px'}),
                ]),
            ]),
            html.Div(children=[
                html.Div('Districts vs Districts', className='mnid-ind-sub'),
                html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                                'gap': '8px'}, children=[
                    dcc.Dropdown(
                        id='mnid-compare-dist-a',
                        options=dist_opts,
                        value=_ALL_DISTRICTS[0] if _ALL_DISTRICTS else None,
                        clearable=False,
                    ),
                    dcc.Dropdown(
                        id='mnid-compare-dist-b',
                        options=dist_opts,
                        value=_ALL_DISTRICTS[1] if len(_ALL_DISTRICTS) > 1 else (_ALL_DISTRICTS[0] if _ALL_DISTRICTS else None),
                        clearable=False,
                    ),
                ]),
                html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr',
                                'gap': '8px', 'marginTop': '6px'}, children=[
                    dcc.Graph(id='mnid-compare-dist-pie-a',
                              config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                              style={'height': '300px'}),
                    dcc.Graph(id='mnid-compare-dist-pie-b',
                              config={'displayModeBar': 'hover', 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
                              style={'height': '300px'}),
                ]),
            ]),
        ]),
    ])

    return html.Div(id='mnid-comparative', children=[
        dcc.Store(id='mnid-compare-store', data=tracked),
        html.Div('COMPARATIVE ANALYSIS', className='mnid-section-lbl'),
        html.Div(className='mnid-chart-grid', children=[compare_selector]),
    ])


# top-bar / alert / KPIs / nav

def _topbar(facility, period, n_tracked, n_await):
    facility_name = _FACILITY_NAMES.get(facility, facility)
    start, end = (period.split(' to ') + [''])[:2]
    return html.Div(className='mnid-topbar', children=[
        html.Div(style={'flex': '1', 'minWidth': '0'}, children=[
            html.Div('STRATEGIC OVERVIEW', className='mnid-topbar-label'),
            html.H1('Maternal and Child Health'),
            html.P(
                'Coverage, quality, and care-phase monitoring for maternal '
                'and neonatal services.',
            ),
        ]),
        html.Div(className='mnid-info-pills', children=[
            html.Div(className='mnid-info-pill', children=[
                html.Div('FACILITY CODE', className='mnid-info-pill-label'),
                html.Div(facility, className='mnid-info-pill-value'),
            ]),
            html.Div(className='mnid-info-pill', children=[
                html.Div('FACILITY', className='mnid-info-pill-label'),
                html.Div(facility_name, className='mnid-info-pill-value'),
            ]),
            html.Div(className='mnid-info-pill', children=[
                html.Div('PERIOD', className='mnid-info-pill-label'),
                html.Div(period,
                         style={'fontSize': '11px', 'fontWeight': '700',
                                'color': TEXT, 'lineHeight': '1.2'}),
            ]),
        ]),
    ])


def _sidebar(facility_code: str) -> html.Div:
    """Left sidebar navigation panel."""
    nav_items = [
        ('Overview',            '#mnid-summary'),
        ('Coverage Indicators', '#mnid-coverage'),
        ('Trends',              '#mnid-trends'),
        ('Heatmap',             '#mnid-heatmap'),
        ('Clinical Analysis',   '#mnid-analysis'),
        ('Compare',             '#mnid-comparative'),
        ('Readiness',           '#mnid-readiness'),
    ]
    return html.Div(className='mnid-sidebar', children=[
        html.Div('Maternal & Child', className='mnid-sidebar-title'),
        html.Div(
            'Maternal, newborn, and postnatal monitoring dashboard.',
            className='mnid-sidebar-desc',
        ),
        html.Div([
            html.A(label, href=href, className='mnid-sidebar-link')
            for label, href in nav_items
        ]),
    ])


def _alert_banner(below, strong):
    if not below:
        return html.Div(className='mnid-alert mnid-alert-ok', children=[
            html.Div(className='mnid-alert-icon',
                     children=html.Span('✓', style={'color':'#fff','fontSize':'10px',
                                                     'fontWeight':'700'})),
            html.P([html.Strong('All tracked indicators on target. '),
                    'Priority coverage is at or above benchmark.']),
        ])
    below_txt  = ', '.join(f'{n} ({p:.0f}%)' for n, p in below)
    strong_txt = ', '.join(strong[:3]) or 'None'
    return html.Div(className='mnid-alert', children=[
        html.Div(className='mnid-alert-icon',
                 children=html.Span('!', style={'color':'#fff','fontSize':'10px',
                                                 'fontWeight':'700'})),
        html.P([html.Strong('Monitor closely. '),
                f'Below benchmark: {below_txt}. Stronger: {strong_txt}.']),
    ])


def _avg_ring(pct: float, color: str) -> html.Div:
    """Prominent donut ring — the ring IS the value display for avg coverage card."""
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
            html.Span(f'{p:.0f}%', style={
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
        _kpi('Tracked',       str(n),           'indicators with live data', 'info',
             bottom_bar=_count_bar(n, n, INFO_C)),
        _kpi('On target',     str(len(on)),      '≥ benchmark',              'ok',
             bottom_bar=_count_bar(len(on),  n, OK_C)),
        _kpi('Performing',    str(len(mon)),     '85–99% of target',         'warn',
             bottom_bar=_count_bar(len(mon), n, WARN_C)),
        _kpi('Needs review',  str(len(crit)),    '< 85% of target',          'danger',
             bottom_bar=_count_bar(len(crit),n, DANGER_C)),
        _kpi('Avg coverage',  '',                'across tracked indicators','info',
             ring=_avg_ring(avg, avg_color)),
    ])


# section anchor wrapper

def _section_anchor(anchor_id):
    """Invisible offset anchor for sticky-nav scrolling."""
    return html.Div(id=anchor_id, className='mnid-section-anchor')


# main entry point

def render_mnid_dashboard(filtered, data_opd, delta_days, config,
                          facility_code, start_date, end_date):
    vt          = config.get('visualization_types', {})
    all_inds    = vt.get('priority_indicators', [])
    supply_inds = vt.get('supply_indicators', [])
    wf_inds     = vt.get('workforce_indicators', [])
    dq_inds     = vt.get('data_quality_indicators', [])
    period      = f'{start_date} to {end_date}'

    tracked  = [i for i in all_inds if i.get('status') == 'tracked']
    awaiting = [i for i in all_inds if i.get('status') == 'awaiting_baseline']

    computed = []
    for ind in tracked:
        num, den, pct = _cov(filtered, ind['numerator_filters'],
                              ind['denominator_filters'])
        computed.append({**ind, 'pct': pct, 'numerator': num, 'denominator': den})

    below  = [(c['label'], c['pct']) for c in computed if c['pct'] < c['target']]
    strong = [c['label'] for c in computed if c['pct'] >= c['target']]

    by_cat = {}
    for ind in all_inds:
        by_cat.setdefault(ind.get('category','Other'), []).append(ind)

    coverage_charts  = _coverage_charts_section(by_cat, filtered)

    # Pre-build analysis charts
    anc_charts    = _anc_charts(filtered)
    labour_charts = _labour_charts(filtered)
    pnc_charts    = _pnc_charts(filtered)
    nb_charts     = _newborn_charts(filtered)

    # All accordion sections open by default
    analysis_acc = [
        _chart_acc_section('ch_anc',    'Antenatal Care',    anc_charts)    if anc_charts    else None,
        _chart_acc_section('ch_labour', 'Labour & Delivery', labour_charts) if labour_charts else None,
        _chart_acc_section('ch_pnc',    'Postnatal Care',    pnc_charts)    if pnc_charts    else None,
        _chart_acc_section('ch_nb',     'Neonatal Care',     nb_charts)     if nb_charts     else None,
    ]
    analysis_acc = [a for a in analysis_acc if a]

    heatmap_div      = _coverage_heatmap_section(all_inds, facility_code)
    comparative_div  = _comparative_analysis_section(all_inds, facility_code)

    def _sec_header(title, count=None, desc=None):
        return html.Div(className='mnid-section-header', children=[
            html.Div([
                html.Span(title, className='mnid-section-header-title'),
                html.Span(f' — {desc}' if desc else '',
                          style={'fontSize': '11px', 'color': MUTED, 'fontWeight': '400'}),
            ]),
            html.Span(f'{count} charts' if count else '',
                      className='mnid-section-header-count'),
        ])

    total_analysis = sum(len(c) for c in [anc_charts, labour_charts, pnc_charts, nb_charts])

    main_content = html.Div(className='mnid-main', children=[

        _topbar(facility_code, period, len(tracked), len(awaiting)),
        _alert_banner(below, strong),

        # ── Overview ────────────────────────────────────────────────────
        _section_anchor('mnid-summary'),
        _sec_header('Overview', desc=f'{len(tracked)} tracked · {len(awaiting)} awaiting'),
        _kpi_row(computed),

        # ── Coverage bars per care phase ─────────────────────────────────
        _section_anchor('mnid-coverage'),
        _sec_header('Coverage Indicators', sum(len(v) for v in by_cat.values()),
                    desc='Coverage % vs target · ▏= target threshold'),
        coverage_charts,

        # ── Trends ───────────────────────────────────────────────────────
        _section_anchor('mnid-trends'),
        _sec_header('Coverage Trends', desc='12-month rolling · dotted line = target'),
        _trend_switcher(filtered, all_inds),

        # ── Coverage heatmap ─────────────────────────────────────────────
        _section_anchor('mnid-heatmap'),
        heatmap_div,

        # ── Clinical Analysis (all sections open) ─────────────────────────
        _section_anchor('mnid-analysis'),
        _sec_header('Clinical Analysis', total_analysis, desc='Care-phase deep-dives'),
        dmc.Accordion(
            multiple=True,
            value=[a.value for a in analysis_acc],
            variant='separated', radius='md', mb='md',
            children=analysis_acc,
            styles={
                'item':    {'backgroundColor': BG, 'border': f'1px solid {BORDER}',
                            'borderRadius': '12px', 'marginBottom': '8px',
                            'boxShadow': '0 1px 3px rgba(0,0,0,0.04)'},
                'control': {'padding': '12px 16px'},
                'panel':   {'padding': '0 16px 2px'},
            },
        ),

        # ── Comparative Analysis ──────────────────────────────────────────
        _section_anchor('mnid-comparative'),
        _sec_header('Facility & District Comparison',
                    desc='Cross-facility and district indicator benchmarking'),
        comparative_div,

        # ── Operational Readiness ─────────────────────────────────────────
        _section_anchor('mnid-readiness'),
        _sec_header('Operational Readiness',
                    desc='Equipment · workforce competency · data quality'),
        _system_readiness(filtered, supply_inds, wf_inds, dq_inds),
    ])

    return html.Div(className='mnid-bg', children=[
        # Scroll-spy components (hidden, fire once on load)
        dcc.Interval(id='mnid-scrollspy-tick', interval=800, max_intervals=1),
        dcc.Store(id='mnid-scrollspy-out'),
        html.Div(className='mnid-shell', children=[
            _sidebar(facility_code),
            main_content,
        ]),
    ])
