"""Service snapshot table/chart views and the Dash callback that switches between them."""
import json
import logging

import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc, callback, callback_context, Input, Output, State, ALL
from dash.exceptions import PreventUpdate

from mnid.charts.chart_helpers import (
    _CAT_LABELS, _CAT_ORDER,
    _cov, _display_pct, _moving_average_values, _target_label,
    _axis_wrap, _TREND_SERIES_PALETTE, CAT_PALETTES,
)
from mnid.core.constants import (
    INFO_C, MUTED, BG, BORDER, TEXT, FONT, GRID_C, DIM,
    FACILITY_NAMES as _FACILITY_NAMES,
)
from mnid.core.indicators import _resolve_category_order

_LOGGER = logging.getLogger(__name__)


def _encounter_slice(df: pd.DataFrame, regex: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    token = str(regex or '').upper()
    if 'Service_Area' in df.columns:
        if 'ANC' in token and 'LABOUR' not in token and 'DELIVERY' not in token:
            return df[df['Service_Area'].astype(str) == 'ANC']
        if 'LABOUR' in token or 'DELIVERY' in token or 'BIRTH' in token:
            return df[df['Service_Area'].astype(str) == 'Labour']
        if 'PNC' in token or 'POSTNATAL' in token:
            return df[df['Service_Area'].astype(str) == 'PNC']
        if 'NEONATAL' in token or 'NEWBORN' in token:
            return df[df['Service_Area'].astype(str) == 'Newborn']
    if 'Encounter' not in df.columns:
        return pd.DataFrame()
    enc = df['Encounter'].fillna('').astype(str)
    return df[enc.str.contains(regex, case=False, na=False)]


def _count_entities(df: pd.DataFrame, col: str) -> int:
    if df is None or df.empty or col not in df.columns:
        return 0
    return int(df[col].dropna().astype(str).nunique())


def _concept_count(df: pd.DataFrame, concept: str, values=None,
                   col: str = 'obs_value_coded', any_value: bool = False) -> int:
    if df is None or df.empty or 'concept_name' not in df.columns:
        return 0
    sub = df[df['concept_name'].fillna('').astype(str) == concept]
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
        for candidate in [col, 'obs_value_coded', 'Value', 'ValueN', 'Value_Name']:
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
                ('ANC records',                   lambda x: _count_entities(x, 'encounter_id')),
                ('Unique ANC clients',             lambda x: _count_entities(x, 'person_id')),
                ('ANC visits',                    lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'ANC VISIT'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Obstetric history recorded',    lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'OBSTETRIC HISTORY'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Gestational age method recorded', lambda x: _concept_count(x, 'Gestational age recorded', any_value=True)),
                ('Pregnancy planned responses',   lambda x: _concept_count(x, 'Pregnancy planned', any_value=True)),
                ('Planned pregnancies',           lambda x: _concept_count(x, 'Pregnancy planned', ['Yes'])),
                ('Danger signs captured',         lambda x: _concept_count(x, 'Danger signs present', any_value=True)),
                ('Tetanus dose status recorded',  lambda x: _concept_count(x, 'Number of tetanus doses', any_value=True)),
                ('2+ tetanus doses recorded',     lambda x: _concept_count(x, 'Number of tetanus doses', ['two doses', 'three doses', 'four doses'], col='obs_value_coded')),
            ],
            'chart_specs': [
                {
                    'id': 'anc_pregnancy_planned', 'label': 'Pregnancy Planned',
                    'title': 'Pregnancy Planned Responses',
                    'total_metric': 'Pregnancy planned responses',
                    'segments': [{'label': 'Planned pregnancies', 'metric': 'Planned pregnancies', 'color': '#0F766E'}],
                    'remainder_label': 'No / other response', 'remainder_color': '#94A3B8',
                },
                {
                    'id': 'anc_tetanus', 'label': 'Tetanus 2+',
                    'title': 'Tetanus Dose Coverage',
                    'total_metric': 'Unique ANC clients',
                    'segments': [{'label': '2+ doses recorded', 'metric': '2+ tetanus doses recorded', 'color': '#0F766E'}],
                    'remainder_label': 'Below 2 doses / not recorded', 'remainder_color': '#94A3B8',
                },
                {
                    'id': 'anc_gestation', 'label': 'Gestation Method',
                    'title': 'Gestational Age Method Documentation',
                    'total_metric': 'Unique ANC clients',
                    'segments': [{'label': 'Gestation method recorded', 'metric': 'Gestational age method recorded', 'color': '#7C3AED'}],
                    'remainder_label': 'Missing gestation method', 'remainder_color': '#CBD5E1',
                },
            ],
        },
        'Labour': {
            'title': 'Labour & Delivery Summary',
            'subtitle': 'Facility rows with labour and delivery indicators as columns.',
            'encounter': 'LABOUR|DELIVERY|BIRTH',
            'metrics': [
                ('Labour records',                lambda x: _count_entities(x, 'encounter_id')),
                ('Unique mothers',                lambda x: _count_entities(x, 'person_id')),
                ('Labour assessments',            lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'LABOUR ASSESSMENT'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Labour visits',                 lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'Labour and delivery visit'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Delivery details recorded',     lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'Delivery Details'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Place of delivery recorded',    lambda x: _concept_count(x, 'Place of delivery', any_value=True)),
                ('This facility deliveries',      lambda x: _concept_count(x, 'Place of delivery', ['This facility', 'this facility'])),
                ('Newborn complications recorded', lambda x: _concept_count(x, 'Newborn baby complications', any_value=True)),
                ('Vitamin K given',               lambda x: _concept_count(x, 'Vitamin K given', ['Yes'])),
                ('Breastfeeding in first hour',   lambda x: _concept_count(x, 'Breast feeding', ['Yes'])),
            ],
            'chart_specs': [
                {
                    'id': 'labour_delivery_location', 'label': 'Delivery Location',
                    'title': 'Place of Delivery',
                    'total_metric': 'Place of delivery recorded',
                    'segments': [{'label': 'This facility', 'metric': 'This facility deliveries', 'color': '#0F766E'}],
                    'remainder_label': 'Other / not recorded', 'remainder_color': '#CBD5E1',
                },
                {
                    'id': 'labour_newborn_care', 'label': 'Immediate Newborn Care',
                    'title': 'Birth Interventions Documented',
                    'total_metric': 'Unique mothers',
                    'segments': [
                        {'label': 'Vitamin K given', 'metric': 'Vitamin K given', 'color': '#C2410C'},
                        {'label': 'Breastfeeding in first hour', 'metric': 'Breastfeeding in first hour', 'color': '#0F766E'},
                    ],
                    'remainder_label': 'Other / not documented', 'remainder_color': '#94A3B8',
                },
            ],
        },
        'Newborn': {
            'title': 'Newborn Summary',
            'subtitle': 'Facility rows with newborn care indicators as columns.',
            'encounter': 'NEONATAL',
            'metrics': [
                ('Neonatal records',          lambda x: _count_entities(x, 'encounter_id')),
                ('Unique babies',             lambda x: _count_entities(x, 'person_id')),
                ('Birth weight recorded',     lambda x: _concept_count(x, 'Birth weight', any_value=True)),
                ('Vitamin K given',           lambda x: _concept_count(x, 'Vitamin K given', ['Yes'])),
                ('Resuscitation recorded',    lambda x: _concept_count(x, 'Neonatal resuscitation provided', any_value=True)),
                ('Active resuscitation',      lambda x: _concept_count(x, 'Neonatal resuscitation provided', ['Yes', 'Stimulation only', 'Bag and mask'])),
                ('Thermal care recorded',     lambda x: _concept_count(x, 'thermal care', any_value=True)),
                ('Mother status recorded',    lambda x: _concept_count(x, 'Mother status', any_value=True)),
            ],
            'chart_specs': [
                {
                    'id': 'newborn_resuscitation', 'label': 'Resuscitation',
                    'title': 'Resuscitation Documentation',
                    'total_metric': 'Resuscitation recorded',
                    'segments': [{'label': 'Active resuscitation', 'metric': 'Active resuscitation', 'color': '#0F766E'}],
                    'remainder_label': 'Other / no action recorded', 'remainder_color': '#CBD5E1',
                },
                {
                    'id': 'newborn_documentation', 'label': 'Documentation',
                    'title': 'Core Newborn Documentation',
                    'total_metric': 'Unique babies',
                    'segments': [{'label': 'Birth weight recorded', 'metric': 'Birth weight recorded', 'color': '#7C3AED'}],
                    'remainder_label': 'Other / missing documentation', 'remainder_color': '#CBD5E1',
                },
            ],
        },
        'PNC': {
            'title': 'PNC Summary',
            'subtitle': 'Facility rows with postnatal care indicators as columns.',
            'encounter': 'PNC|POSTNATAL|POST.NATAL',
            'metrics': [
                ('PNC records',              lambda x: _count_entities(x, 'encounter_id')),
                ('Unique mothers',           lambda x: _count_entities(x, 'person_id')),
                ('PNC visits',               lambda x: _count_entities(x[x['Encounter_Source'].fillna('').astype(str) == 'PNC VISIT'] if 'Encounter_Source' in x.columns else x, 'encounter_id')),
                ('Babies reviewed',          lambda x: _concept_count(x, 'Status of baby', any_value=True)),
                ('Mother outcome recorded',  lambda x: _concept_count(x, 'Status of the mother', any_value=True)),
                ('Mothers alive',            lambda x: _concept_count(x, 'Status of the mother', ['Alive'])),
                ('Maternal deaths',          lambda x: _concept_count(x, 'Status of the mother', ['Death', 'Died', 'Dead'])),
                ('Baby outcome recorded',    lambda x: _concept_count(x, 'Status of baby', any_value=True)),
                ('Babies alive',             lambda x: _concept_count(x, 'Status of baby', ['Alive'])),
                ('PNC within 48 hours',      lambda x: _concept_count(x, 'Postnatal check period', ['Up to 48 hrs or before discharge'])),
                ('Immunisation recorded',    lambda x: _concept_count(x, 'Immunisation given', any_value=True)),
                ('BCG given',                lambda x: _concept_count(x, 'Immunisation given', ['BCG'])),
            ],
            'chart_specs': [
                {
                    'id': 'pnc_maternal_outcomes', 'label': 'Maternal Outcomes',
                    'title': 'Maternal PNC Outcomes',
                    'total_metric': 'Mother outcome recorded',
                    'segments': [
                        {'label': 'Mothers alive', 'metric': 'Mothers alive', 'color': '#0F766E'},
                        {'label': 'Maternal deaths', 'metric': 'Maternal deaths', 'color': '#DB2777'},
                    ],
                    'remainder_label': 'Other outcomes', 'remainder_color': '#CBD5E1',
                },
                {
                    'id': 'pnc_baby_outcomes', 'label': 'Baby Outcomes',
                    'title': 'Baby Outcomes During PNC',
                    'total_metric': 'Baby outcome recorded',
                    'segments': [
                        {'label': 'Babies alive', 'metric': 'Babies alive', 'color': '#0F766E'},
                        {'label': 'Babies reviewed', 'metric': 'Babies reviewed', 'color': '#2563EB'},
                    ],
                    'remainder_label': 'Other outcomes', 'remainder_color': '#CBD5E1',
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
            'title':      spec['title'],
            'subtitle':   spec['subtitle'],
            'columns':    [label for label, _calc in spec['metrics']],
            'rows':       section_rows,
            'chart_specs': spec.get('chart_specs', []),
        }
    return payload


def _service_table_fig(section: dict) -> go.Figure:
    rows    = section.get('rows', [])
    columns = section.get('columns', [])
    header_values = ['Facility Name'] + columns
    cell_values   = [[row.get('facility', '') for row in rows]]
    for idx, _col in enumerate(columns):
        cell_values.append([
            f"{int(row.get('values', [])[idx]):,}" if idx < len(row.get('values', [])) else '0'
            for row in rows
        ])
    fig = go.Figure(data=[go.Table(
        columnwidth=[0.24] + [0.12] * len(columns),
        header=dict(values=header_values, fill_color='#F8FAFC', line_color='#E2E8F0',
                    align='left', font=dict(color='#0F172A', size=11, family=FONT), height=34),
        cells=dict(
            values=cell_values, fill_color='#FFFFFF', line_color='#E2E8F0',
            align=['left'] + ['right'] * len(columns),
            font=dict(
                color=[['#334155'] * len(rows)] + [['#0F172A'] * len(rows) for _ in columns],
                size=[11] + [12] * len(columns), family=FONT,
            ),
            height=38,
        ),
    )])
    fig.update_layout(
        title=dict(
            text=(
                f"<b>{section.get('title', 'Service Summary')}</b>"
                f"<br><span style='color:#94A3B8;font-size:11px;font-weight:500'>"
                f"{section.get('subtitle', '')}</span>"
            ),
            x=0, xanchor='left', font=dict(size=15, color=TEXT, family=FONT),
        ),
        margin=dict(l=0, r=0, t=56, b=0),
        height=max(340, 108 + (len(rows) * 38)),
        paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF',
    )
    return fig


def _service_stack_fig(section: dict, chart_id: str | None = None) -> go.Figure:
    rows        = section.get('rows', [])
    chart_specs = section.get('chart_specs', []) or []
    fig = go.Figure()
    if not rows or not chart_specs:
        fig.add_annotation(text='No stacked metric available for this selection',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF',
                          height=320, margin=dict(l=8, r=8, t=32, b=8))
        return fig

    spec         = next((item for item in chart_specs if item.get('id') == chart_id), chart_specs[0])
    columns      = section.get('columns', [])
    metric_index = {label: idx for idx, label in enumerate(columns)}
    facilities   = [row.get('facility', '') for row in rows]

    seg_payloads   = []
    remainder_vals = []
    for segment in spec.get('segments', []):
        seg_idx = metric_index.get(segment.get('metric'))
        vals = [max(int((row.get('values', [])[seg_idx] if seg_idx is not None and seg_idx < len(row.get('values', [])) else 0) or 0), 0) for row in rows]
        seg_payloads.append({**segment, 'values': vals})

    total_metric = spec.get('total_metric')
    total_idx    = metric_index.get(total_metric) if total_metric else None
    if total_idx is not None:
        totals = [max(int((row.get('values', [])[total_idx] if total_idx < len(row.get('values', [])) else 0) or 0), 0) for row in rows]
    else:
        totals = [sum(seg['values'][ri] for seg in seg_payloads) for ri in range(len(rows))]

    for ri in range(len(rows)):
        subtotal = sum(seg['values'][ri] for seg in seg_payloads)
        remainder_vals.append(max(totals[ri] - subtotal, 0))

    for segment in seg_payloads:
        fig.add_trace(go.Bar(
            x=facilities, y=segment['values'], name=segment.get('label', ''),
            marker=dict(color=segment.get('color', INFO_C)),
            hovertemplate='%{x}<br>' + f"{segment.get('label', '')}: " + '%{y:,}<extra></extra>',
        ))
    if spec.get('remainder_label') and any(remainder_vals):
        fig.add_trace(go.Bar(
            x=facilities, y=remainder_vals, name=spec.get('remainder_label', 'Other'),
            marker=dict(color=spec.get('remainder_color', '#CBD5E1')),
            hovertemplate='%{x}<br>' + f"{spec.get('remainder_label', 'Other')}: " + '%{y:,}<extra></extra>',
        ))

    fig.update_layout(
        paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF',
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        title=dict(
            text=(
                f"<b>{spec.get('title', section.get('title', 'Service Snapshot'))}</b>"
                f"<br><span style='color:#94A3B8;font-size:11px;font-weight:500'>{section.get('subtitle', '')}</span>"
            ),
            x=0, xanchor='left', font=dict(size=15, color=TEXT, family=FONT),
        ),
        margin=dict(l=0, r=0, t=56, b=24),
        height=max(340, 280 + (18 if len(rows) > 4 else 0)),
        barmode='stack',
        legend=dict(orientation='h', x=0, y=1.12, xanchor='left', font=dict(size=10, color=DIM)),
        xaxis=dict(showgrid=False, zeroline=False, showline=False, tickfont=dict(size=10, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED), title=dict(text='Clients', font=dict(size=10, color=MUTED))),
    )
    return fig


def _service_stack_overview_fig(section: dict) -> go.Figure:
    chart_specs = section.get('chart_specs', []) or []
    rows        = section.get('rows', [])
    fig = go.Figure()

    if not chart_specs or not rows:
        fig.add_annotation(text='No stacked indicators configured for this category',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF',
                          height=340, margin=dict(l=8, r=8, t=32, b=8))
        return fig

    columns      = section.get('columns', [])
    metric_index = {label: idx for idx, label in enumerate(columns)}
    labels       = [_axis_wrap(spec.get('label', spec.get('title', 'Indicator')), width=22, max_lines=2) for spec in chart_specs]
    facilities   = [row.get('facility', '') for row in rows]

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
            seg_idx   = metric_index.get(segment.get('metric'))
            seg_total = sum(
                max(int(row.get('values', [])[seg_idx] or 0), 0)
                for row in rows
                if seg_idx is not None and seg_idx < len(row.get('values', []))
            ) if seg_idx is not None else 0
            segment_entries.append({
                'label':  segment.get('label', ''),
                'metric': segment.get('metric', ''),
                'color':  segment.get('color', INFO_C),
                'value':  seg_total,
            })

        total_metric = spec.get('total_metric')
        total_idx    = metric_index.get(total_metric) if total_metric else None
        if total_idx is not None:
            total_val = sum(
                max(int(row.get('values', [])[total_idx] or 0), 0)
                for row in rows
                if total_idx < len(row.get('values', []))
            )
        else:
            total_val = sum(item['value'] for item in segment_entries)

        subtotal      = sum(item['value'] for item in segment_entries)
        remainder_val = max(total_val - subtotal, 0)
        if spec.get('remainder_label'):
            segment_entries.append({
                'label':  spec.get('remainder_label', 'Other'),
                'metric': total_metric or '',
                'color':  spec.get('remainder_color', '#CBD5E1'),
                'value':  remainder_val,
            })
        spec_summaries.append({
            'label':    _axis_wrap(spec.get('label', spec.get('title', 'Indicator')), width=22, max_lines=2),
            'title':    spec.get('title', spec.get('label', 'Indicator')),
            'total':    total_val,
            'segments': [e for e in segment_entries if e['value'] > 0],
        })

    max_segments = max((len(item['segments']) for item in spec_summaries), default=0)
    for seg_idx in range(max_segments):
        x_vals, y_vals, colors, names, customdata = [], [], [], [], []
        for summary in spec_summaries:
            if seg_idx >= len(summary['segments']):
                continue
            entry = summary['segments'][seg_idx]
            x_vals.append(entry['value'])
            y_vals.append(summary['label'])
            colors.append(entry['color'])
            names.append(entry['label'])
            customdata.append([summary['title'], entry['label'], summary['total'], entry['metric']])
        if x_vals:
            trace_name = next((n for n in names if n), f'Series {seg_idx + 1}')
            fig.add_trace(go.Bar(
                x=x_vals, y=y_vals, orientation='h', name=trace_name,
                marker=dict(color=colors), customdata=customdata,
                hovertemplate='%{customdata[0]}<br>Series: %{customdata[1]}<br>Count: %{x:,}<br>Reference total: %{customdata[2]:,}<extra></extra>',
            ))

    fig.update_layout(
        paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF',
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        title=dict(
            text=(
                f"<b>{section.get('title', 'Service Snapshot')} Indicator Comparison</b>"
                f"<br><span style='color:#94A3B8;font-size:11px;font-weight:500'>{subtitle}</span>"
            ),
            x=0, xanchor='left', font=dict(size=15, color=TEXT, family=FONT),
        ),
        margin=dict(l=0, r=0, t=62, b=72),
        height=max(352, 116 + len(spec_summaries) * 58),
        barmode='group',
        legend=dict(orientation='h', x=0, y=-0.18, xanchor='left', yanchor='top',
                    font=dict(size=10, color=DIM), bgcolor='rgba(255,255,255,0.9)'),
        xaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED), title=dict(text='Clients', font=dict(size=10, color=MUTED))),
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


def _location_trend_fig(
    df: pd.DataFrame, cat_inds: list, cat: str,
    chart_type: str = 'line',
    scope_meta: dict | None = None,
) -> go.Figure:
    """Location-level trend figure for a service category (up to 2 indicators)."""
    fig = go.Figure()
    if not len(df) or not cat_inds or 'Date' not in df.columns:
        fig.add_annotation(text='No trend data available for this selection',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, height=340, margin=dict(l=8, r=8, t=12, b=24))
        return fig

    d2 = df.copy()
    d2['Date'] = pd.to_datetime(d2['Date'], errors='coerce')
    d2 = d2.dropna(subset=['Date'])
    if d2.empty:
        fig.add_annotation(text='No dated records available for run chart view',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, height=340, margin=dict(l=8, r=8, t=12, b=24))
        return fig

    span_days = max(int((d2['Date'].max() - d2['Date'].min()).days), 0)
    if span_days <= 45:
        freq, tickformat, period_label = 'D', '%d %b', 'daily'
    elif span_days <= 180:
        freq, tickformat, period_label = 'W-MON', '%d %b', 'weekly'
    else:
        freq, tickformat, period_label = 'M', '%b %y', 'monthly'

    d2['_period'] = d2['Date'].dt.to_period(freq)
    periods = sorted(d2['_period'].dropna().unique())
    if not periods:
        fig.add_annotation(text='No time periods available for run chart view',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, height=340, margin=dict(l=8, r=8, t=12, b=24))
        return fig

    color_cycle = CAT_PALETTES.get(cat, _TREND_SERIES_PALETTE)
    active_inds = cat_inds[:2]

    for idx, ind in enumerate(active_inds):
        xs, ys = [], []
        for p in periods:
            period_df = d2[d2['_period'] == p]
            _, den, pct = _cov(period_df, ind['numerator_filters'], ind['denominator_filters'])
            xs.append(pd.Period(p, freq).to_timestamp().to_pydatetime())
            ys.append(_display_pct(pct) if den > 0 else None)
        moving_average, _ = _moving_average_values(ys, period_label)
        if not any(y is not None for y in moving_average):
            continue

        color       = color_cycle[idx % len(color_cycle)]
        series_name = ind['label']
        clean_pairs = [(x, y, raw) for x, y, raw in zip(xs, moving_average, ys) if y is not None]
        clean_xs    = [x for x, _, _ in clean_pairs]
        clean_ys    = [y for _, y, _ in clean_pairs]
        clean_raw   = [raw for _, _, raw in clean_pairs]

        if chart_type == 'bar':
            fig.add_trace(go.Bar(
                x=clean_xs, y=clean_ys, name=series_name,
                marker=dict(color=color, line=dict(color=color, width=1)),
                customdata=[[raw] for raw in clean_raw],
                hovertemplate=f'%{{x|%d %b %Y}}<br>{series_name} Moving Avg: %{{y:.1f}}%<br>Raw Coverage: %{{customdata[0]:.1f}}%<extra></extra>',
            ))
        else:
            fig.add_trace(go.Scatter(
                x=clean_xs, y=clean_ys, name=series_name,
                mode='lines+markers',
                line=dict(color=color, width=2.8, shape='linear'),
                marker=dict(size=6, color=color, line=dict(color='#fff', width=1.4)),
                connectgaps=False,
                customdata=[[raw] for raw in clean_raw],
                hovertemplate=f'%{{x|%d %b %Y}}<br>{series_name} Moving Avg: %{{y:.1f}}%<br>Raw Coverage: %{{customdata[0]:.1f}}%<extra></extra>',
            ))
            if idx == 0 and clean_xs:
                _tgt = ind.get('target')
                if _tgt is not None:
                    fig.add_trace(go.Scatter(
                        x=clean_xs, y=[_tgt] * len(clean_xs), mode='lines',
                        line=dict(color='#A1A1AA', width=1.5, dash='dot'),
                        name=_target_label(ind), showlegend=True,
                        hovertemplate=f'Target: {_tgt:.0f}%<extra></extra>',
                    ))
                key_pts = [(clean_xs[0], clean_ys[0], clean_raw[0])]
                if len(clean_xs) > 1:
                    key_pts.append((clean_xs[-1], clean_ys[-1], clean_raw[-1]))
                peak_idx = clean_ys.index(max(clean_ys))
                peak_pt  = (clean_xs[peak_idx], clean_ys[peak_idx], clean_raw[peak_idx])
                if peak_pt not in key_pts:
                    key_pts.append(peak_pt)
                fig.add_trace(go.Scatter(
                    x=[x for x, _, _ in key_pts], y=[y for _, y, _ in key_pts],
                    mode='markers+text', text=[f'{y:.1f}' for _, y, _ in key_pts],
                    textposition='top center', marker=dict(size=8, color='black'), showlegend=False,
                    customdata=[[raw] for _, _, raw in key_pts],
                    hovertemplate=f'%{{x|%d %b %Y}}<br>{series_name} Moving Avg: %{{y:.1f}}%<br>Raw Coverage: %{{customdata[0]:.1f}}%<extra></extra>',
                ))

    if not fig.data:
        fig.add_annotation(text='No run chart points available for the selected indicator',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))

    chart_title = active_inds[0]['label'] if len(active_inds) == 1 else f'{_CAT_LABELS.get(cat, cat)} related indicators'
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TEXT, size=11),
        hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        height=360, margin=dict(l=8, r=8, t=12, b=24),
        barmode='group' if chart_type == 'bar' else None,
        title=dict(text=f'{chart_title} ({period_label})', x=0.01, xanchor='left',
                   font=dict(size=14, color=TEXT, family=FONT)),
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   tickformat=tickformat, tickfont=dict(size=10, color=MUTED),
                   title=dict(text='Date', font=dict(size=10, color=MUTED))),
        yaxis=dict(showgrid=True, gridcolor=GRID_C, zeroline=False, showline=False,
                   tickfont=dict(size=10, color=MUTED), range=[0, 105],
                   title=dict(text='Coverage %', font=dict(size=10, color=MUTED))),
        legend=dict(font=dict(size=10, color=DIM), bgcolor='rgba(0,0,0,0)',
                    orientation='h', x=0, y=1.05, xanchor='left', yanchor='bottom'),
        hovermode='closest' if chart_type == 'bar' else 'x unified',
    )
    return fig


def _service_table_switcher(
    df: pd.DataFrame,
    categories: list | None = None,
    default_cat: str | None = None,
    scope_meta: dict | None = None,
) -> html.Div:
    payload   = _service_table_payload(df, scope_meta)
    cat_order = [c for c in _resolve_category_order([{'category': k} for k in payload.keys()], categories) if c in payload]
    default_cat     = default_cat if default_cat in cat_order else (cat_order[0] if cat_order else 'ANC')
    default_section = payload.get(default_cat, {'rows': []})
    return html.Div(className='mnid-card', style={'marginBottom': '12px'}, children=[
        html.Div(
            style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between',
                   'marginBottom': '8px', 'gap': '12px', 'flexWrap': 'wrap'},
            children=[
                html.Div('SERVICE SNAPSHOT', className='mnid-section-lbl', style={'marginBottom': '0'}),
                html.Div(
                    style={'display': 'flex', 'alignItems': 'center', 'gap': '10px', 'flexWrap': 'wrap'},
                    children=[
                        html.Button(
                            type='button', id='mnid-service-table-toggle',
                            className='mnid-trend-toggle is-line', n_clicks=0,
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
                    ],
                ),
            ],
        ),
        dcc.Store(id='mnid-service-table-store', data=payload),
        dcc.Store(id='mnid-service-table-active-cat', data=default_cat),
        dcc.Store(id='mnid-service-table-cats-store', data=cat_order),
        dcc.Store(id='mnid-service-table-view-store', data='table'),
        html.Div(id='mnid-service-table-content', children=_service_snapshot_view(default_section, 'table')),
    ])


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
    cat        = active_cat if active_cat in categories else (categories[0] if categories else 'ANC')
    view_mode  = view_mode or 'table'
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

    tables  = stored_tables or {}
    section = tables.get(cat) or next(iter(tables.values()), {'rows': []})
    classes = ['mnid-filter-btn active' if c == cat else 'mnid-filter-btn' for c in categories]
    content      = _service_snapshot_view(section, view_mode)
    toggle_class = 'mnid-trend-toggle is-bar' if view_mode == 'chart' else 'mnid-trend-toggle is-line'
    toggle_text  = 'Chart' if view_mode == 'chart' else 'Table'
    return content, cat, classes, view_mode, toggle_class, toggle_text
