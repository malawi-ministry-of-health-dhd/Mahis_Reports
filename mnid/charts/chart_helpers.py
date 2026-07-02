"""
Chart helper functions for the MNID dashboard.

Contains low-level computation utilities, chart-building helpers,
moving-average logic, and shared module-level palette/layout constants.
"""
import pandas as pd
import plotly.graph_objects as go
import statistics as _stats
import logging
from datetime import datetime
from dash import html, dcc
from helpers.helpers import create_count_from_config
from helpers.visualizations import _apply_filter
from config import DATE_ as _DATE_COL
from mnid.core.constants import (
    OK_C, WARN_C, DANGER_C, INFO_C, MUTED, GRID_C, BG, BORDER, TEXT, DIM, FONT,
    CAT_PALETTES, FACILITY_NAMES as _FACILITY_NAMES,
)

_LOGGER = logging.getLogger(__name__)
_MNID_WARNED_MESSAGES: set = set()


def _grouped_filter_counts(df: pd.DataFrame, group_cols: list[str], cfg: dict) -> pd.Series:
    """Count rows matching a numerator/denominator filter config, grouped by group_cols.

    Same end result as calling create_count_from_config once per group, just done in
    one pass: filter the whole dataframe (still via _apply_filter, same as the config
    helper would use), dedupe, then group. group_cols is folded into the dedupe key
    so someone who shows up in two groups on the same date still counts once per group,
    same as if each group had been filtered separately.
    """
    unique_col = cfg.get('unique') or 'person_id'
    data = df
    for i in range(1, 11):
        var = cfg.get(f'variable{i}')
        val = cfg.get(f'value{i}')
        if not var or not val:
            continue
        data = _apply_filter(data, var, val)
        if data.empty:
            break
    if data.empty or unique_col not in data.columns or _DATE_COL not in data.columns:
        return pd.Series(dtype='int64')
    data = data.drop_duplicates(subset=group_cols + [unique_col, _DATE_COL])
    return data.groupby(group_cols).size()

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

_CAT_LABELS = {'ANC': 'ANC', 'Labour': 'Labour & Delivery', 'Newborn': 'Newborn', 'PNC': 'PNC'}
_CAT_ORDER  = ['ANC', 'Labour', 'Newborn', 'PNC']

CHART_HEIGHT_SM = 220
CHART_HEIGHT_MD = 320
CHART_HEIGHT_LG = 420
CHART_HEIGHT_XL = 520


def _clamp_chart_height(value: int, min_height: int = CHART_HEIGHT_SM, max_height: int = CHART_HEIGHT_LG) -> int:
    return max(min_height, min(int(value), max_height))


def _graph_style(height: int) -> dict:
    fixed_height = int(height)
    return {
        'height': f'{fixed_height}px',
        'width': '100%',
        'minHeight': f'{fixed_height}px',
        'maxHeight': f'{fixed_height}px',
    }


def _graph_scroll_wrap(child, outer_height: int):
    fixed_height = int(outer_height)
    return html.Div(
        style={
            'height': f'{fixed_height}px',
            'width': '100%',
            'minHeight': f'{fixed_height}px',
            'maxHeight': f'{fixed_height}px',
            'overflowY': 'auto',
            'overflowX': 'hidden',
        },
        children=[child],
    )


def _warn_once(message: str) -> None:
    if message in _MNID_WARNED_MESSAGES:
        return
    _MNID_WARNED_MESSAGES.add(message)
    _LOGGER.warning(message)


def _moving_average_window(length: int, grain: str | None = None) -> int:
    grain_value = str(grain or '').lower()
    if grain_value in {'d', 'day', 'daily'}:
        return max(1, min(7, length))
    return max(1, min(3, length))


def _moving_average_values(values, grain: str | None = None):
    numeric = pd.Series(values, dtype='float64')
    window = _moving_average_window(len(numeric), grain)
    smoothed = numeric.rolling(window=window, min_periods=1).mean()
    return [None if pd.isna(value) else float(value) for value in smoothed.tolist()], window


def _filter_columns_missing(df: pd.DataFrame, cfg: dict | None) -> list[str]:
    if not cfg:
        return []
    missing = []
    for i in range(1, 11):
        var = cfg.get(f'variable{i}')
        val = cfg.get(f'value{i}')
        if not var or not val:
            continue
        if var not in df.columns:
            missing.append(str(var))
    return missing

# MNID data helpers

def _cov(df, n_cfg, d_cfg):
    num_missing = _filter_columns_missing(df, n_cfg)
    den_missing = _filter_columns_missing(df, d_cfg)
    if num_missing:
        _warn_once(f"MNID numerator filter references missing columns: {', '.join(num_missing)}")
    if den_missing:
        _warn_once(f"MNID denominator filter references missing columns: {', '.join(den_missing)}")
    try:
        num = int(create_count_from_config(df, n_cfg) or 0)
    except Exception as exc:
        _warn_once(f"MNID numerator count failed for config {n_cfg}: {exc}")
        num = 0
    try:
        den = int(create_count_from_config(df, d_cfg) or 0)
    except Exception as exc:
        _warn_once(f"MNID denominator count failed for config {d_cfg}: {exc}")
        den = 0
    if den:
        pct = round(min(num / den * 100, 100.0), 1)
    else:
        pct = 0.0
    return num, den, pct


def _monthly(df, n_cfg, d_cfg, n=6):
    if 'Date' not in df.columns or not len(df): return []
    try:
        periods = pd.to_datetime(df['Date'], errors='coerce').dt.to_period('M')
        months = sorted(periods.dropna().unique())[-n:]
        return [{'x': datetime(m.year, m.month, 1),
                 'pct': _cov(df[periods == m], n_cfg, d_cfg)[2]}
                for m in months]
    except Exception as exc:
        _warn_once(f"MNID monthly series build failed for numerator {n_cfg} / denominator {d_cfg}: {exc}")
        return []


def _target_mode(ind_or_mode) -> str:
    if isinstance(ind_or_mode, dict):
        mode = str(ind_or_mode.get('target_mode') or 'max').strip().lower()
    else:
        mode = str(ind_or_mode or 'max').strip().lower()
    return mode if mode in {'max', 'min'} else 'max'


def _is_inverse_indicator(ind: dict) -> bool:
    return _target_mode(ind) == 'min'


def _css(pct, tgt, mode='max'):
    mode = _target_mode(mode)
    if mode == 'min':
        warn_threshold = tgt * 1.15 if tgt else 0
        return 'ok' if pct <= tgt else ('warn' if pct <= warn_threshold else 'danger')
    return 'ok' if pct >= tgt else ('warn' if pct >= tgt * 0.85 else 'danger')


def _on_target(pct, tgt, mode='max') -> bool:
    return _css(pct, tgt, mode) == 'ok'


def _target_attainment_pct(pct, tgt, mode='max') -> float:
    mode = _target_mode(mode)
    pct = float(pct or 0.0)
    tgt = float(tgt or 0.0)
    if mode == 'min':
        if pct <= tgt:
            return 100.0
        if pct <= 0:
            return 100.0
        return max(0.0, min(100.0, (tgt / pct) * 100.0))
    if tgt <= 0:
        return 0.0
    return max(0.0, min(100.0, (pct / tgt) * 100.0))


def _target_label(ind: dict) -> str:
    prefix = '<=' if _is_inverse_indicator(ind) else ''
    return f'Target {prefix}{ind["target"]}%'
_CLR = {'ok': OK_C, 'warn': WARN_C, 'danger': DANGER_C, 'info': INFO_C}


def _display_pct(pct):
    if pct is None:
        return None
    try:
        v = float(pct)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN check (NaN != NaN is True)
        return None
    return max(0.0, min(v, 100.0))


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


def _flag_value_counts(df, flag_col: str, unique_col: str = 'person_id',
                       yes_label: str = 'Screened', no_label: str = 'Not screened'):
    if flag_col not in df.columns or unique_col not in df.columns or not len(df):
        return pd.DataFrame(columns=['label', 'n'])
    people = (
        df[[unique_col, flag_col]]
        .dropna(subset=[unique_col])
        .assign(**{flag_col: lambda x: x[flag_col].fillna('').astype(str).str.strip()})
        .drop_duplicates(subset=[unique_col])
    )
    if people.empty:
        return pd.DataFrame(columns=['label', 'n'])
    labels = people[flag_col].eq('Yes').map({True: yes_label, False: no_label})
    out = labels.value_counts().rename_axis('label').reset_index(name='n')
    return out.sort_values('n', ascending=False)


def _monthly_visits(df, encounter_val, unique_col='person_id'):
    sub = pd.DataFrame()
    if 'Encounter' in df.columns:
        sub = df[df['Encounter'] == encounter_val]
    if sub.empty and 'Service_Area' in df.columns:
        area_map = {
            'ANC VISIT': 'ANC',
            'LABOUR AND DELIVERY': 'Labour',
            'POSTNATAL CARE': 'PNC',
            'NEONATAL CARE': 'Newborn',
        }
        service_area = area_map.get(str(encounter_val or '').strip().upper())
        if service_area:
            sub = df[df['Service_Area'].astype(str) == service_area]
    if not len(sub):
        return pd.DataFrame(columns=['month', 'n', 'freq'])
    dates = pd.to_datetime(sub['Date'], errors='coerce').dropna()
    if dates.empty:
        return pd.DataFrame(columns=['month', 'n', 'freq'])
    span_days = max(int((dates.max() - dates.min()).days), 0)
    if span_days <= 45:
        freq, fmt = 'D', 'day'
        sub['month'] = dates.dt.floor('D')
    elif span_days <= 180:
        freq, fmt = 'W', 'week'
        sub['month'] = dates.dt.to_period('W').dt.start_time
    else:
        freq, fmt = 'M', 'month'
        sub['month'] = dates.dt.to_period('M').dt.start_time
    out = sub.groupby('month')[unique_col].nunique().reset_index()
    out.columns = ['month', 'n']
    out['freq'] = fmt
    return out.sort_values('month')


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
    clean = monthly_df.dropna(subset=['n']).copy()
    if clean.empty:
        return None

    freq = clean['freq'].iloc[0] if 'freq' in clean.columns else 'month'
    if freq == 'day':
        tickfmt = '%d %b'
        hover_fmt = '%{x|%d %b %Y}: %{y}'
    elif freq == 'week':
        tickfmt = '%d %b'
        hover_fmt = '%{x|%d %b %Y}: %{y}'
    else:
        tickfmt = '%b %y'
        hover_fmt = '%{x|%b %Y}: %{y}'

    moving_average, ma_window = _moving_average_values(clean['n'].tolist(), freq)

    fig = go.Figure(go.Scatter(
        x=clean['month'], y=moving_average,
        mode='lines+markers',
        line=dict(color=color, width=2.5, shape='linear'),
        marker=dict(size=6, color=color, line=dict(color='#fff', width=1.35)),
        customdata=clean[['n']].to_numpy(),
        hovertemplate=hover_fmt + '<br>Moving Avg: %{y:.1f}<br>Raw value: %{customdata[0]}<extra></extra>',
    ))

    key_points = []
    start_point = (clean.iloc[0]['month'], moving_average[0], clean.iloc[0]['n'])
    end_point = (clean.iloc[-1]['month'], moving_average[-1], clean.iloc[-1]['n'])
    peak_index = pd.Series(moving_average).idxmax()
    peak_point = (clean.iloc[peak_index]['month'], moving_average[peak_index], clean.iloc[peak_index]['n'])
    for point in [start_point, peak_point, end_point]:
        if point not in key_points:
            key_points.append(point)

    fig.add_trace(go.Scatter(
        x=[x for x, _, _ in key_points],
        y=[y for _, y, _ in key_points],
        mode='markers+text',
        text=[f'{y:.1f}' for _, y, _ in key_points],
        textposition='top center',
        textfont=dict(size=9, color='#374151'),
        marker=dict(size=8, color='#1e293b'),
        showlegend=False,
        customdata=[[raw] for _, _, raw in key_points],
        hovertemplate=hover_fmt + '<br>Moving Avg: %{y:.1f}<br>Raw value: %{customdata[0]}<extra></extra>',
    ))

    fig.update_layout(
        **_CHART_LAYOUT,
        title=dict(text=title, font=dict(size=12, color='#444441', family=FONT),
                   x=0, xanchor='left', y=0.98),
        height=220,
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickformat=tickfmt, tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False,
                   showline=False, tickfont=dict(size=10, color=MUTED),
                   title=dict(text=y_label, font=dict(size=10, color=MUTED))),
    )
    return fig


def _monthly_concept_rate(df, concept, positive_values=None, title='', target=None,
                          color='#2563EB', target_col='obs_value_coded'):
    if df is None or df.empty or 'Date' not in df.columns or 'concept_name' not in df.columns:
        return None
    sub = df[df['concept_name'].fillna('').astype(str) == concept]
    if sub.empty:
        return None
    col = target_col if target_col in sub.columns else ('obs_value_coded' if 'obs_value_coded' in sub.columns else None)
    if not col:
        return None

    dates = pd.to_datetime(sub['Date'], errors='coerce').dropna()
    if dates.empty:
        return None
    span_days = max(int((dates.max() - dates.min()).days), 0)
    if span_days <= 45:
        period_grain = 'daily'
        sub['_m'] = dates.dt.floor('D')
        tickfmt = '%d %b'
        hover_fmt = '%{x|%d %b %Y}<br>%{y:.0f}%'
    elif span_days <= 180:
        period_grain = 'weekly'
        sub['_m'] = dates.dt.to_period('W').dt.start_time
        tickfmt = '%d %b'
        hover_fmt = '%{x|%d %b %Y}<br>%{y:.0f}%'
    else:
        period_grain = 'monthly'
        sub['_m'] = dates.dt.to_period('M').dt.start_time
        tickfmt = '%b %y'
        hover_fmt = '%{x|%b %Y}<br>%{y:.0f}%'

    periods = sorted(sub['_m'].dropna().unique())
    if not periods:
        return None

    xs = list(periods)
    ys = []
    for p in periods:
        month_df = sub[sub['_m'] == p]
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

    moving_average, ma_window = _moving_average_values(ys, period_grain)
    valid = [(x, y, raw) for x, y, raw in zip(xs, moving_average, ys) if y is not None]
    if not valid:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=moving_average,
        mode='lines+markers',
        line=dict(color=color, width=2.5, shape='linear'),
        marker=dict(size=6, color=color, line=dict(color='#fff', width=1.35)),
        connectgaps=False,
        customdata=[[raw] for raw in ys],
        hovertemplate=hover_fmt + '<br>Moving Avg: %{y:.1f}%<br>Raw Coverage: %{customdata[0]:.1f}%<extra></extra>',
        showlegend=False,
    ))

    if target is not None:
        fig.add_trace(go.Scatter(
            x=xs, y=[target] * len(xs),
            mode='lines',
            line=dict(color='#A1A1AA', width=1.5, dash='dot'),
            hovertemplate='Target: %{y:.0f}%<extra></extra>',
            showlegend=False,
        ))

    key_pts = []
    start = valid[0]
    end = valid[-1]
    peak = max(valid, key=lambda p: p[1])
    for pt in [start, peak, end]:
        if pt not in key_pts:
            key_pts.append(pt)
    fig.add_trace(go.Scatter(
        x=[p[0] for p in key_pts],
        y=[p[1] for p in key_pts],
        mode='markers+text',
        text=[f'{p[1]:.1f}%' for p in key_pts],
        textposition='top center',
        textfont=dict(size=9, color='#374151'),
        marker=dict(size=7, color='#1e293b'),
        showlegend=False,
        customdata=[[p[2]] for p in key_pts],
        hovertemplate=hover_fmt + '<br>Moving Avg: %{y:.1f}%<br>Raw Coverage: %{customdata[0]:.1f}%<extra></extra>',
    ))

    fig.update_layout(
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        font=dict(family=FONT, color=TEXT, size=11),
        margin=dict(l=12, r=8, t=28, b=26),
        height=210,
        title=dict(text=title, x=0, xanchor='left', font=dict(size=12, color='#444441', family=FONT)),
        xaxis=dict(showgrid=False, zeroline=False, showline=False, tickformat=tickfmt,
                   tickfont=dict(size=9, color=MUTED)),
        yaxis=dict(range=[0, 115], showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=9, color=MUTED), ticksuffix='%',
                   title=dict(text='Coverage', font=dict(size=9, color=MUTED))),
    )
    return fig


def _monthly_concept_mix_fig(df, concept, categories, title, target_col='obs_value_coded'):
    if df is None or df.empty or 'Date' not in df.columns or 'concept_name' not in df.columns:
        return None
    sub = df[df['concept_name'].fillna('').astype(str) == concept]
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
            month_df = sub[sub['_m'] == m]
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
    sub = df[df['concept_name'].fillna('').astype(str) == concept]
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
