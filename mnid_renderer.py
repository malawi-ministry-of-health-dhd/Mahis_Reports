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
from dash import html, dcc
import dash_mantine_components as dmc
from helpers import create_count_from_config
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime


# ══ palette ════════════════════════════════════════════════════════════════════
OK_C    = '#3B6D11';  WARN_C  = '#BA7517';  DANGER_C = '#E24B4A'
INFO_C  = '#185FA5';  MUTED   = '#B4B2A9';  GRID_C   = '#F1EFE8'
BG      = '#fff';     BORDER  = '#E0DED6';  TEXT     = '#1A1A18'
DIM     = '#73726C';  FONT    = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'

CAT_PALETTES = {
    'ANC':     ['#185FA5','#2E86D4','#5BA3E4','#89C0F0','#B5D8F8','#1A3F6E'],
    'Labour':  ['#BA7517','#D4881A','#E8A830','#F5C658','#FAD97A','#7C4D0A','#A35F10'],
    'Newborn': ['#3B6D11','#4E8E18','#68B022','#86C83A','#A8D96E','#2A5009','#64A51F'],
    'PNC':     ['#7C3AED','#9D5CF0','#B683F4','#CFAAF8'],
}

HEATMAP_CS = [
    [0.00, '#FCE4E4'],
    [0.40, '#E24B4A'],
    [0.65, '#BA7517'],
    [0.80, '#FAC775'],
    [0.88, '#C0DD97'],
    [1.00, '#3B6D11'],
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


# ══ data helpers ═══════════════════════════════════════════════════════════════

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


# ══ themed chart builders ══════════════════════════════════════════════════════

def _empty_card(title):
    return html.Div(className='mnid-chart-card', children=[
        html.Div(title, className='mnid-card-title'),
        html.Div('No data available', className='mnid-ind-note',
                 style={'padding': '24px 0', 'textAlign': 'center'}),
    ])


def _chart_card(title, fig):
    return html.Div(className='mnid-chart-card', children=[
        dcc.Graph(figure=fig, config={'displayModeBar': False},
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


# ══ TREND SWITCHER ════════════════════════════════════════════════════════════

def _trend_switcher(df: pd.DataFrame, indicators: list) -> html.Div:
    """
    One Plotly figure with all indicator trends.
    Category buttons (ANC / Labour / Newborn / PNC) toggle which traces are visible.
    hovermode='x unified' — NO staticPlot.
    """
    tracked = [i for i in indicators if i.get('status') == 'tracked']
    by_cat = {}
    for ind in tracked:
        by_cat.setdefault(ind.get('category','Other'), []).append(ind)

    cat_order = ['ANC', 'Labour', 'Newborn', 'PNC']

    fig = go.Figure()
    trace_cats = []

    for cat in cat_order:
        palette = CAT_PALETTES.get(cat, [INFO_C])
        for j, ind in enumerate(by_cat.get(cat, [])):
            pts = _monthly(df, ind['numerator_filters'], ind['denominator_filters'])
            if len(pts) < 2:
                trace_cats.append(cat)
                fig.add_trace(go.Scatter(
                    x=[], y=[], name=ind['label'],
                    visible=(cat == 'ANC'),
                    showlegend=True,
                    line=dict(color=palette[j % len(palette)], width=2),
                ))
                continue
            xs = [p['x'] for p in pts]
            ys = [p['pct'] for p in pts]
            c  = palette[j % len(palette)]
            r, g, b = int(c[1:3],16), int(c[3:5],16), int(c[5:7],16)
            fig.add_trace(go.Scatter(
                x=xs, y=ys, name=ind['label'],
                visible=(cat == 'ANC'),
                mode='lines+markers',
                line=dict(color=c, width=2.5, shape='spline'),
                marker=dict(size=6, color=c, line=dict(color='#fff', width=1.5)),
                fill='tozeroy', fillcolor=f'rgba({r},{g},{b},0.05)',
                hovertemplate=f'%{{x|%b %Y}}<br>{ind["label"]}: %{{y:.0f}}%<extra></extra>',
            ))
            trace_cats.append(cat)
            if cat == 'ANC':
                fig.add_shape(type='line',
                              x0=xs[0], x1=xs[-1],
                              y0=ind['target'], y1=ind['target'],
                              line=dict(color=c, width=1, dash='dot'),
                              layer='below')

    # Build category toggle buttons
    buttons = []
    for cat in cat_order:
        vis = [tc == cat for tc in trace_cats]
        buttons.append(dict(
            label=cat if cat != 'Labour' else 'Labour & Delivery',
            method='update',
            args=[{'visible': vis},
                  {'title.text': f'{cat} — Coverage Trend (%)'}],
        ))

    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        height=300,
        margin=dict(l=4, r=4, t=64, b=20),
        title=dict(text='ANC — Coverage Trend (%)',
                   font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.97),
        updatemenus=[dict(
            type='buttons', direction='right',
            buttons=buttons,
            x=0, y=1.22, xanchor='left', yanchor='top',
            pad=dict(r=6, t=0),
            bgcolor='#F5F4F0', bordercolor=BORDER, borderwidth=1,
            font=dict(size=11, color=TEXT, family=FONT),
            showactive=True,
            active=0,
        )],
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickformat='%b %y', tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False,
                   showline=False, tickfont=dict(size=10, color=MUTED),
                   range=[0, 105],
                   title=dict(text='Coverage %', font=dict(size=10, color=MUTED))),
        legend=dict(font=dict(size=10, color=DIM), bgcolor='rgba(0,0,0,0)',
                    orientation='v', x=1.01, y=1, xanchor='left', yanchor='top'),
        hovermode='x unified',
    )

    return html.Div(className='mnid-card', style={'marginBottom': '12px'}, children=[
        html.Div('COVERAGE TREND', className='mnid-section-lbl'),
        dcc.Graph(figure=fig, config={'displayModeBar': False},
                  style={'height': '300px'}),
    ])


# ══ HEATMAP ════════════════════════════════════════════════════════════════════

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


def _build_heatmap(df_full: pd.DataFrame, indicators: list, facility_code: str) -> html.Div:
    """
    Multi-view indicator coverage heatmap.
    4 views × 3 year filters = 12 traces.  Only one visible at a time.
    Views: Monthly | District Facilities | All Districts | All Facilities
    Year filters: All | 2025 | 2026
    """
    # Load full MCH data
    try:
        df_all = pd.read_parquet('data/latest_data_opd.parquet')
        mch_full = df_all[df_all['Program'].str.contains('Maternal|Neonatal', case=False, na=False)].copy()
        if 'Date' in mch_full.columns:
            mch_full['Date'] = pd.to_datetime(mch_full['Date'], errors='coerce')
    except Exception:
        mch_full = pd.DataFrame()

    tracked = [i for i in indicators if i.get('status') == 'tracked']
    if not tracked:
        return html.Div()

    cat_order = ['ANC', 'Labour', 'Newborn', 'PNC']
    sorted_inds = []
    for cat in cat_order:
        sorted_inds.extend([i for i in tracked if i.get('category') == cat])
    # any uncategorised
    sorted_inds.extend([i for i in tracked if i not in sorted_inds])

    y_labels = [i['label'][:28] for i in sorted_inds]
    n_inds = len(sorted_inds)

    current_district = _FACILITY_DISTRICT.get(facility_code, '')
    district_facs = [f for f in _ALL_FACILITIES
                     if _FACILITY_DISTRICT.get(f) == current_district]

    def _year_slice(df, year_val):
        if year_val is None or not len(df) or 'Date' not in df.columns:
            return df
        return df[df['Date'].dt.year == year_val]

    # Pre-compute all 4 views × 3 year filters = 12 sets of (x_labels, z)
    year_filters = [None, 2025, 2026]
    all_traces_data = []  # (x_labels, z, view_idx, year_idx)

    for year_idx, year_val in enumerate(year_filters):
        mch_y = _year_slice(mch_full, year_val)

        # View 0: This Facility — Monthly
        fac_df = mch_y[mch_y['Facility_CODE'] == facility_code] if len(mch_y) else mch_y
        if len(fac_df):
            x0, z0 = _matrix_monthly(fac_df, sorted_inds)
        else:
            x0, z0 = [], []
        all_traces_data.append((x0, z0, 0, year_idx))

        # View 1: District Facilities (same district as current)
        x1 = [f'{f}*' if f == facility_code else f for f in district_facs]
        z1 = _matrix_by_group(mch_y, sorted_inds, 'Facility_CODE', district_facs) if len(mch_y) else []
        all_traces_data.append((x1, z1, 1, year_idx))

        # View 2: All Districts
        x2 = _ALL_DISTRICTS[:]
        z2 = _matrix_by_group(mch_y, sorted_inds, 'District', _ALL_DISTRICTS) if len(mch_y) else []
        all_traces_data.append((x2, z2, 2, year_idx))

        # View 3: All Facilities
        x3 = [f'{f}*' if f == facility_code else f for f in _ALL_FACILITIES]
        z3 = _matrix_by_group(mch_y, sorted_inds, 'Facility_CODE', _ALL_FACILITIES) if len(mch_y) else []
        all_traces_data.append((x3, z3, 3, year_idx))

    # Trace index = view_idx * 3 + year_idx  (view outer, year inner)
    # total: 12 traces
    n_total = 12

    fig = go.Figure()

    for year_idx in range(3):
        for view_idx in range(4):
            trace_idx = view_idx * 3 + year_idx
            # find matching data
            entry = next((e for e in all_traces_data
                          if e[2] == view_idx and e[3] == year_idx), None)
            if entry is None or not entry[0]:
                x_labels, z = [], [[None]*1 for _ in sorted_inds]
            else:
                x_labels, z = entry[0], entry[1]

            fig.add_trace(go.Heatmap(
                z=z,
                x=x_labels,
                y=y_labels,
                colorscale=HEATMAP_CS,
                zmin=0, zmax=100,
                colorbar=dict(
                    thickness=14,
                    title=dict(text='Coverage %', side='right',
                               font=dict(size=10, color=DIM)),
                    tickfont=dict(size=9, color=DIM),
                    len=0.9,
                ),
                hovertemplate='%{y}<br>%{x}: %{z:.0f}%<extra></extra>',
                visible=(trace_idx == 0),  # only first trace visible initially
                showscale=(trace_idx == 0),
            ))

    height = max(n_inds * 26 + 120, 400)

    # Build view buttons (updatemenus row 1)
    view_labels = ['This Facility — Monthly', 'District Facilities', 'All Districts', 'All Facilities']
    view_buttons = []
    for vi in range(4):
        # when this view button is clicked, keep the current year filter
        # we activate traces for this view across all years, then hide all but
        # the one matching the active year — but since year state is not stored,
        # clicking a view button defaults to year=All (year_idx=0)
        vis = [False] * n_total
        active_trace = vi * 3 + 0  # default to year=All
        vis[active_trace] = True
        # update colorbar visibility: only visible trace shows scale
        showscale_updates = [False] * n_total
        showscale_updates[active_trace] = True
        xangle = 0 if vi == 0 else -40
        view_buttons.append(dict(
            label=view_labels[vi],
            method='update',
            args=[
                {'visible': vis, 'showscale': showscale_updates},
                {'xaxis.tickangle': xangle},
            ],
        ))

    # Build year buttons (updatemenus row 2)
    year_labels = ['All', '2025', '2026']
    year_buttons = []
    for yi in range(3):
        # default to view=0 (monthly) when clicking year; ideally we'd keep
        # current view but without callbacks we default to monthly + chosen year
        vis = [False] * n_total
        active_trace = 0 * 3 + yi
        vis[active_trace] = True
        showscale_updates = [False] * n_total
        showscale_updates[active_trace] = True
        year_buttons.append(dict(
            label=year_labels[yi],
            method='update',
            args=[
                {'visible': vis, 'showscale': showscale_updates},
                {},
            ],
        ))

    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        height=height,
        margin=dict(l=220, r=100, t=90, b=60),
        xaxis=dict(
            tickangle=0,
            tickfont=dict(size=10, color=DIM),
            showgrid=False,
            side='bottom',
        ),
        yaxis=dict(
            tickfont=dict(size=10, color=DIM),
            showgrid=False,
            autorange='reversed',
        ),
        updatemenus=[
            dict(
                type='buttons', direction='right',
                buttons=view_buttons,
                x=0, y=1.12, xanchor='left', yanchor='top',
                pad=dict(r=6, t=0),
                bgcolor='#F5F4F0', bordercolor=BORDER, borderwidth=1,
                font=dict(size=10, color=TEXT, family=FONT),
                showactive=True,
                active=0,
            ),
            dict(
                type='buttons', direction='right',
                buttons=year_buttons,
                x=0, y=1.04, xanchor='left', yanchor='top',
                pad=dict(r=6, t=0),
                bgcolor='#F5F4F0', bordercolor=BORDER, borderwidth=1,
                font=dict(size=10, color=TEXT, family=FONT),
                showactive=True,
                active=0,
            ),
        ],
        annotations=[
            dict(
                text='* = current facility',
                x=1, y=-0.08,
                xref='paper', yref='paper',
                xanchor='right', yanchor='top',
                showarrow=False,
                font=dict(size=9, color=MUTED),
            )
        ],
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
    )

    return html.Div(id='mnid-heatmap', className='mnid-card',
                    style={'marginBottom': '12px'}, children=[
        html.Div('INDICATOR COVERAGE HEATMAP', className='mnid-section-lbl'),
        html.P(
            'Colour: green ≥ target · amber = performing · red = below benchmark · * = current facility',
            style={'fontSize': '10px', 'color': MUTED, 'marginBottom': '6px'},
        ),
        dcc.Graph(
            figure=fig,
            config={'displayModeBar': True,
                    'modeBarButtonsToRemove': ['select2d', 'lasso2d']},
            style={'height': f'{height}px'},
        ),
    ])


# ══ indicator cards ════════════════════════════════════════════════════════════

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


# ══ accordion helpers ══════════════════════════════════════════════════════════

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


# ══ themed analysis charts ══════════════════════════════════════════════════════

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
        'Home': DANGER_C, 'Referral facility': WARN_C,
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
        'Live births': OK_C, 'Fresh stillbirth': DANGER_C,
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
        'Alive': OK_C, 'Died': DANGER_C, 'Referred': WARN_C,
    })
    if fig: charts.append(_chart_card('', fig))

    vc = _value_counts(df, 'Status of baby')
    fig = _donut(vc, 'Baby Final Status', color_map={
        'Alive': OK_C, 'Died': DANGER_C, 'Referred': WARN_C,
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


# ══ system readiness ══════════════════════════════════════════════════════════

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


# ══ top-bar / alert / KPIs / nav ══════════════════════════════════════════════

def _topbar(facility, period, n_tracked, n_await):
    return html.Div(className='mnid-topbar', children=[
        html.Div([
            html.H1('Maternal & Neonatal Integrated Dashboard'),
            html.P(f'Facility: {facility}  ·  {period}'),
        ]),
        html.Div(className='mnid-pills', children=[
            html.Span('M-NID', className='mnid-pill mnid-pill-blue'),
            html.Span(f'{n_tracked} tracked',
                      className='mnid-pill mnid-pill-green'),
            html.Span(f'{n_await} awaiting baseline',
                      className='mnid-pill mnid-pill-amber'),
        ]),
    ])


def _nav_bar():
    """Sticky pill-row navigation with anchor links to each dashboard section."""
    nav_items = [
        ('Summary',   '#mnid-summary'),
        ('Coverage',  '#mnid-coverage'),
        ('Trends',    '#mnid-trends'),
        ('Heatmap',   '#mnid-heatmap'),
        ('Analysis',  '#mnid-analysis'),
        ('Readiness', '#mnid-readiness'),
    ]
    return html.Div(
        className='mnid-nav',
        style={
            'position': 'sticky',
            'top': '0',
            'zIndex': '100',
        },
        children=[
            html.A(label, href=href, className='mnid-nav-btn')
            for label, href in nav_items
        ],
    )


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


def _kpi(label, value, sub, cls):
    return html.Div(className=f'mnid-kpi {cls}', children=[
        html.Div(label, className='kpi-lbl'),
        html.Div(value, className='kpi-val'),
        html.Div(sub,   className='kpi-sub'),
    ])


def _kpi_row(computed):
    on   = [c for c in computed if c['pct'] >= c['target']]
    mon  = [c for c in computed if c['target']*.85 <= c['pct'] < c['target']]
    crit = [c for c in computed if c['pct'] < c['target']*.85]
    avg  = round(sum(c['pct'] for c in computed)/len(computed),0) if computed else 0
    return html.Div(className='mnid-kpi-row', children=[
        _kpi('Indicators tracked', str(len(computed)), 'with live data',  'info'),
        _kpi('On target',          str(len(on)),       '≥ benchmark',      'ok'),
        _kpi('Performing',         str(len(mon)),      '85–99% of target', 'warn'),
        _kpi('Needs review',       str(len(crit)),     '< 85% of target',  'danger'),
        _kpi('Avg coverage',       f'{avg:.0f}%',      'tracked only',     'info'),
    ])


# ══ section anchor wrapper ════════════════════════════════════════════════════

def _section_anchor(anchor_id):
    """Invisible offset anchor for sticky-nav scrolling."""
    return html.Div(id=anchor_id, className='mnid-section-anchor')


# ══ main entry point ═══════════════════════════════════════════════════════════

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

    acc_items = [
        _acc_section('anc',     'Antenatal Care (ANC)',    by_cat.get('ANC',    []), filtered, True),
        _acc_section('labour',  'Labour & Delivery',       by_cat.get('Labour', []), filtered),
        _acc_section('newborn', 'Newborn Care',            by_cat.get('Newborn',[]), filtered),
        _acc_section('pnc',     'Postnatal Care (PNC)',    by_cat.get('PNC',    []), filtered),
    ]

    # Pre-build analysis charts
    anc_charts    = _anc_charts(filtered)
    labour_charts = _labour_charts(filtered)
    pnc_charts    = _pnc_charts(filtered)
    nb_charts     = _newborn_charts(filtered)

    analysis_acc = [
        _chart_acc_section('ch_anc',    'ANC Analysis',               anc_charts)    if anc_charts    else None,
        _chart_acc_section('ch_labour', 'Labour & Delivery Analysis',  labour_charts) if labour_charts else None,
        _chart_acc_section('ch_pnc',    'PNC Analysis',               pnc_charts)    if pnc_charts    else None,
        _chart_acc_section('ch_nb',     'Newborn Analysis',           nb_charts)     if nb_charts     else None,
    ]
    analysis_acc = [a for a in analysis_acc if a]

    heatmap_div = _build_heatmap(filtered, all_inds, facility_code)

    return html.Div(className='mnid-bg', children=[

        _topbar(facility_code, period, len(tracked), len(awaiting)),
        _nav_bar(),
        _alert_banner(below, strong),

        # ── Summary ──────────────────────────────────────────────────
        _section_anchor('mnid-summary'),
        html.Div('SUMMARY', className='mnid-section-lbl'),
        _kpi_row(computed),

        # ── Coverage ─────────────────────────────────────────────────
        _section_anchor('mnid-coverage'),
        html.Div('COVERAGE INDICATORS BY CARE PHASE',
                 className='mnid-section-lbl', style={'marginTop': '8px'}),
        dmc.Accordion(
            multiple=True, value=['anc'], variant='separated', radius='md', mb='md',
            children=acc_items,
            styles={
                'item':    {'backgroundColor': BG, 'border': f'0.5px solid {BORDER}',
                            'borderRadius': '10px', 'marginBottom': '6px'},
                'control': {'padding': '12px 16px'},
                'panel':   {'padding': '0 16px 2px'},
            },
        ),

        # ── Trends ───────────────────────────────────────────────────
        _section_anchor('mnid-trends'),
        _trend_switcher(filtered, all_inds),

        # ── Heatmap ──────────────────────────────────────────────────
        # id='mnid-heatmap' is set inside _build_heatmap
        heatmap_div,

        # ── Analysis ─────────────────────────────────────────────────
        _section_anchor('mnid-analysis'),
        html.Div('CLINICAL ANALYSIS', className='mnid-section-lbl'),
        dmc.Accordion(
            multiple=False, value='ch_anc', variant='separated', radius='md', mb='md',
            children=analysis_acc,
            styles={
                'item':    {'backgroundColor': BG, 'border': f'0.5px solid {BORDER}',
                            'borderRadius': '10px', 'marginBottom': '6px'},
                'control': {'padding': '12px 16px'},
                'panel':   {'padding': '0 16px 2px'},
            },
        ),

        # ── Readiness ────────────────────────────────────────────────
        _section_anchor('mnid-readiness'),
        _system_readiness(filtered, supply_inds, wf_inds, dq_inds),
    ])
