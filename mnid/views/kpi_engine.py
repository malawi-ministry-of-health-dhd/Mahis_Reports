"""KPI computation — indicator content builder, coverage aggregation, heatmap store."""
import json
import logging
import time as _time
from pathlib import Path

import pandas as pd
from dash import html

from mnid.core.cache import (
    _dk, _trim_cache, _agg_version_stamp,
    _resolve_scope_filters,
    _MNID_EXECUTIVE_DISK_CACHE, _MNID_UI_CACHE_TTL_SECONDS,
    _network_df_cache, _NETWORK_DF_CACHE_MAX,
    _get_network_df_from_state,
)
from mnid.aggregation.store import (
    get_aggregate as _get_aggregate,
    query_coverage as _agg_coverage,
    _floor_to_period as _agg_floor_period,
    _candidate_grains as _agg_candidate_grains,
    resolve_indicator_id as _agg_resolve_id,
)
from mnid.charts.chart_helpers import (
    _CAT_LABELS, _CAT_ORDER,
    _cov, _css, _moving_average_values, _display_pct,
    _target_attainment_pct, _on_target, _axis_wrap,
)
from mnid.core.constants import MUTED, BG, BORDER, TEXT, FONT, GRID_C, DIM
from mnid.core.indicators import (
    _resolve_category_order, _resolve_runtime_mnid_indicators,
)
from mnid.charts.coverage import (
    _coverage_charts_section, _coverage_heatmap_section,
    _comparative_analysis_section, _validate_indicator_configs,
)
from mnid.charts.layout import (
    _topbar, _sidebar, _alert_banner, _section_anchor,
    _kpi_row, _hero_donut_row,
)
from mnid.charts.heatmap import (
    _compute_heatmap_store, _compute_heatmap_store_from_agg,
)
from mnid.core.data_utils import (
    prepare_mnid_dataframe as _prepare_mnid_dataframe,
    _remember_ui_payload,
)

_LOGGER = logging.getLogger(__name__)


def _aggregate_grain_for_window(start_ts, end_ts) -> str:
    """Pick the cheapest aggregate grain that still covers the visible window."""
    try:
        if start_ts is None or end_ts is None:
            return 'daily'
        span_days = max(int((pd.Timestamp(end_ts) - pd.Timestamp(start_ts)).days), 0)
    except Exception:
        return 'daily'
    if span_days <= 45:
        return 'daily'
    if span_days <= 180:
        return 'weekly'
    return 'monthly'


def _build_agg_batch(agg_df: pd.DataFrame, start, end, grain: str,
                     fac_filter=None, dist_filter=None) -> dict:
    """
    Pre-aggregate a date window into a {(indicator_id, grain): (num, den, pct)} dict.

    Single groupby replaces N individual query_coverage calls (~40-60x faster).
    """
    try:
        grains = _agg_candidate_grains(grain)
        floor = min(_agg_floor_period(start, g) for g in grains)
        sub = agg_df[
            agg_df['grain'].isin(grains)
            & (agg_df['period_start'] >= floor)
            & (agg_df['period_start'] <= pd.Timestamp(end))
        ]
        if fac_filter:
            sub = sub[sub['facility_code'].isin([str(f) for f in fac_filter])]
        elif dist_filter:
            sub = sub[sub['district'].isin([str(d) for d in dist_filter])]
        if sub.empty:
            return {}
        grouped = sub.groupby(['indicator_id', 'grain'], as_index=False)[['numerator', 'denominator']].sum()
        num = grouped['numerator'].astype(int)
        den = grouped['denominator'].astype(int)
        den_safe = den.where(den > 0, 1)
        pct = (num / den_safe * 100).clip(upper=100.0).round(1).where(den > 0, 0.0)
        return {
            (str(iid), g): (int(n), int(d), float(p))
            for iid, g, n, d, p in zip(grouped['indicator_id'], grouped['grain'], num, den, pct)
        }
    except Exception:
        return {}


def _batch_cov(batch: dict, ind_id: str, grain_fallbacks: list) -> tuple:
    """Look up (num, den, pct) from a pre-built batch dict with grain fallback."""
    iid = str(ind_id)
    for g in grain_fallbacks:
        v = batch.get((iid, g))
        if v and v[1] > 0:
            return v
    return 0, 0, 0.0


def _programme_activity_counts(df: pd.DataFrame) -> dict[str, int]:
    """Count distinct persons for each key programme activity in the filtered df."""
    if df is None or df.empty:
        return {k: 0 for k in (
            'anc_clients', 'anc_visit_clients', 'anc_complications',
            'labour_admissions', 'anc_not_reaching_labour',
            'pnc_clients', 'labour_not_reaching_pnc',
            'labour_visit_documented', 'labour_complications',
            'pnc_visit_documented', 'pnc_mother_complications',
            'pnc_newborn_complications', 'pnc_maternal_deaths',
            'pnc_newborn_deaths', 'pnc_mother_status_records',
            'pnc_baby_status_records', 'stillbirths', 'live_births',
            'newborn_neonatal_deaths', 'newborn_status_records',
            'newborn_complications_at_birth', 'newborn_ikmc_initiated',
        )}

    valid_person = df['person_id'].notna() if 'person_id' in df.columns else pd.Series(False, index=df.index)
    service_col = (
        'Service_Area' if 'Service_Area' in df.columns
        else ('Reporting_Program' if 'Reporting_Program' in df.columns else 'Program')
    )
    service_upper = (
        df[service_col].fillna('').astype(str).str.upper()
        if service_col in df.columns else pd.Series('', index=df.index)
    )
    anc_scope    = service_upper.str.contains('ANC', na=False)
    labour_scope = service_upper.str.contains('LABOUR|DELIVERY', na=False)
    pnc_scope    = service_upper.str.contains('PNC|POSTNATAL', na=False)
    newborn_scope = service_upper.str.contains('NEWBORN|NEONATAL', na=False)

    def _count_people(mask: pd.Series) -> int:
        if 'person_id' not in df.columns:
            return 0
        scoped = mask.fillna(False) & valid_person
        if not scoped.any():
            return 0
        return int(df.loc[scoped, 'person_id'].astype(str).nunique())

    def _pid_set(mask: pd.Series) -> set[str]:
        if 'person_id' not in df.columns:
            return set()
        scoped = mask.fillna(False) & valid_person
        if not scoped.any():
            return set()
        return set(df.loc[scoped, 'person_id'].astype(str))

    anc_pids    = _pid_set(anc_scope)
    labour_pids = _pid_set(labour_scope)
    pnc_pids    = _pid_set(pnc_scope)

    if {'concept_name', 'obs_value_coded', 'person_id'}.issubset(df.columns):
        concept_name    = df['concept_name'].fillna('').astype(str).str.strip()
        obs_value_lower = df['obs_value_coded'].fillna('').astype(str).str.strip().str.lower()
        has_positive_obs = ~obs_value_lower.isin(['', 'no', 'none', 'negative', 'unknown'])
        death_obs        = obs_value_lower.isin(['death', 'died', 'dead', 'deceased'])
    else:
        concept_name     = pd.Series('', index=df.index)
        obs_value_lower  = pd.Series('', index=df.index)
        has_positive_obs = pd.Series(False, index=df.index)
        death_obs        = pd.Series(False, index=df.index)

    anc_visit_clients = len(anc_pids)
    if 'mnid_anc_visit_documented' in df.columns:
        anc_visit_clients = _count_people(df['mnid_anc_visit_documented'].eq('Yes'))

    anc_complications = 0
    if {'concept_name', 'obs_value_coded', 'person_id'}.issubset(df.columns):
        anc_complications = _count_people(
            anc_scope & concept_name.eq('Obstetric complications') & has_positive_obs
        )

    complications_mask = pd.Series(False, index=df.index)
    for col in ['mnid_labour_maternal_sepsis', 'mnid_labour_pph', 'mnid_labour_eclampsia']:
        if col in df.columns:
            complications_mask |= df[col].eq('Yes')
    labour_complications = _count_people(complications_mask)

    stillbirths = 0
    if 'mnid_labour_stillbirth' in df.columns:
        stillbirths = _count_people(df['mnid_labour_stillbirth'].eq('Yes'))
    live_births = max(len(labour_pids) - stillbirths, 0)

    labour_visit_documented = 0
    if 'mnid_labour_visit_documented' in df.columns:
        labour_visit_documented = _count_people(df['mnid_labour_visit_documented'].eq('Yes'))

    pnc_visit_documented = 0
    if 'mnid_pnc_visit_documented' in df.columns:
        pnc_visit_documented = _count_people(df['mnid_pnc_visit_documented'].eq('Yes'))

    pnc_mother_complications = pnc_newborn_complications = 0
    pnc_maternal_deaths = pnc_newborn_deaths = 0
    pnc_mother_status_records = pnc_baby_status_records = 0
    newborn_status_records = newborn_neonatal_deaths = 0

    if {'concept_name', 'obs_value_coded', 'person_id'}.issubset(df.columns):
        pnc_mother_complications = _count_people(
            pnc_scope & concept_name.eq('Postnatal complications') & has_positive_obs)
        pnc_newborn_complications = _count_people(
            pnc_scope & concept_name.eq('Newborn baby complications') & has_positive_obs)
        pnc_mother_status_records = _count_people(pnc_scope & concept_name.eq('Status of the mother'))
        pnc_baby_status_records   = _count_people(pnc_scope & concept_name.eq('Status of baby'))
        pnc_maternal_deaths = _count_people(
            pnc_scope & concept_name.eq('Status of the mother') & death_obs)
        pnc_newborn_deaths = _count_people(
            pnc_scope & concept_name.eq('Status of baby') & death_obs)
        newborn_status_records = _count_people(newborn_scope & concept_name.eq('Status of baby'))
        newborn_neonatal_deaths = _count_people(
            newborn_scope & concept_name.eq('Status of baby') & death_obs)

    newborn_complications_mask = pd.Series(False, index=df.index)
    for col in ['mnid_newborn_birth_asphyxia', 'mnid_newborn_sepsis', 'mnid_newborn_jaundice']:
        if col in df.columns:
            newborn_complications_mask |= df[col].eq('Yes')
    newborn_complications_at_birth = _count_people(newborn_complications_mask)

    newborn_ikmc_initiated = 0
    if 'mnid_newborn_kmc' in df.columns:
        newborn_ikmc_initiated = _count_people(df['mnid_newborn_kmc'].eq('Yes'))

    return {
        'anc_clients':                   len(anc_pids),
        'anc_visit_clients':             anc_visit_clients,
        'anc_complications':             anc_complications,
        'labour_admissions':             len(labour_pids),
        'anc_not_reaching_labour':       len(anc_pids - labour_pids),
        'pnc_clients':                   len(pnc_pids),
        'labour_not_reaching_pnc':       len(labour_pids - pnc_pids),
        'labour_visit_documented':       labour_visit_documented,
        'labour_complications':          labour_complications,
        'pnc_visit_documented':          pnc_visit_documented,
        'pnc_mother_complications':      pnc_mother_complications,
        'pnc_newborn_complications':     pnc_newborn_complications,
        'pnc_maternal_deaths':           pnc_maternal_deaths,
        'pnc_newborn_deaths':            pnc_newborn_deaths,
        'pnc_mother_status_records':     pnc_mother_status_records,
        'pnc_baby_status_records':       pnc_baby_status_records,
        'stillbirths':                   stillbirths,
        'live_births':                   live_births,
        'newborn_neonatal_deaths':       newborn_neonatal_deaths,
        'newborn_status_records':        newborn_status_records,
        'newborn_complications_at_birth': newborn_complications_at_birth,
        'newborn_ikmc_initiated':        newborn_ikmc_initiated,
    }


def _load_mnid_report_config(report_name: str) -> dict | None:
    try:
        config_path = Path(__file__).resolve().parents[2] / 'data' / 'visualizations' / 'validated_dashboard.json'
        with open(config_path, 'r') as fh:
            dashboards = json.load(fh)
    except Exception:
        return None
    return next(
        (d for d in dashboards
         if d.get('dashboard_type') == 'mnid' and d.get('report_name') == report_name),
        None,
    )


def _build_mnid_indicator_content(network_df: pd.DataFrame, config: dict,
                                  facility_code, start_date, end_date,
                                  scope_meta: dict | None = None,
                                  include_content: bool = True) -> dict:
    # Normalise period bounds once — used for date filtering and aggregate queries.
    try:
        _s = pd.to_datetime(start_date).normalize() if start_date else None
        _e = (
            (pd.to_datetime(end_date).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
            if end_date else (
                network_df['Date'].max() if 'Date' in network_df.columns and not network_df.empty
                else pd.Timestamp.now()
            )
        )
    except Exception:
        _s = _e = None

    facility_df = network_df
    if _s is not None and 'Date' in network_df.columns and not network_df.empty:
        try:
            date_mask = (network_df['Date'] >= _s) & (network_df['Date'] <= _e)
            facility_df = network_df[date_mask]
        except Exception:
            facility_df = network_df

    selected_facilities, selected_facility_codes, selected_districts = _resolve_scope_filters(
        network_df, scope_meta,
    )
    if selected_facilities and 'Facility' in facility_df.columns:
        facility_df = facility_df[facility_df['Facility'].isin(selected_facilities)]
    elif selected_districts and 'District' in facility_df.columns:
        facility_df = facility_df[facility_df['District'].isin(selected_districts)]

    selected_program = (scope_meta or {}).get('mnid_categories')
    selected_program = selected_program[0] if selected_program else 'All'
    facility_df.attrs['mnid_program'] = selected_program
    network_df.attrs['mnid_program'] = selected_program
    if network_df.empty:
        network_df = facility_df

    vt = config.get('visualization_types', {})
    all_inds    = config.get('priority_indicators') or vt.get('priority_indicators', [])
    supply_inds = config.get('supply_indicators') or vt.get('supply_indicators', [])
    wf_inds     = config.get('workforce_indicators') or vt.get('workforce_indicators', [])
    dq_inds     = config.get('data_quality_indicators') or vt.get('data_quality_indicators', [])
    period      = f'{start_date} to {end_date}'
    period_note = (scope_meta or {}).get('data_period_note')

    requested_categories = (scope_meta or {}).get('mnid_categories')
    config_categories    = config.get('mnid_categories')
    if config_categories:
        effective_categories = [c for c in (requested_categories or []) if c in config_categories] or config_categories
    else:
        effective_categories = requested_categories

    all_inds = _resolve_runtime_mnid_indicators(all_inds, facility_df, effective_categories)
    removed_indicator_labels = {
        'Gestation weeks recorded',
        'Neonatal enrolment documented',
        'Screened for infection',
    }
    all_inds = [i for i in all_inds if i.get('label') not in removed_indicator_labels]
    _validate_indicator_configs(all_inds)
    category_order = _resolve_category_order(all_inds, effective_categories)
    if category_order:
        allowed = set(category_order)
        all_inds = [i for i in all_inds if i.get('category') in allowed]

    overview_inds = [i for i in all_inds if i.get('status') == 'overview_only']
    display_inds  = [i for i in all_inds if i.get('status') != 'overview_only']

    import hashlib, pickle
    payload_key = hashlib.md5(pickle.dumps(
        (len(network_df), tuple(network_df.columns.tolist()) if not network_df.empty else (),
         start_date, end_date, tuple(category_order)),
        protocol=4,
    )).hexdigest()[:16] + f'_{start_date}_{end_date}'

    tracked  = [i for i in display_inds if i.get('status') == 'tracked']
    awaiting = [i for i in display_inds if i.get('status') == 'awaiting_baseline']
    default_cat = category_order[0] if category_order else 'ANC'

    if category_order == ['Newborn']:
        dashboard_title    = 'Neonatal Care Dashboard'
        dashboard_subtitle = 'Program monitoring for admissions, outcomes, clinical interventions, coverage, and readiness.'
        dashboard_theme    = 'newborn'
    elif set(category_order) == {'ANC', 'Labour', 'PNC'}:
        dashboard_title    = 'Maternal Care Health Dashboard'
        dashboard_subtitle = 'ANC, labour, and postnatal performance, comparison, coverage, and readiness.'
        dashboard_theme    = 'default'
    else:
        dashboard_title    = f"{config.get('report_name', 'Maternal and Child Health')} Indicators"
        dashboard_subtitle = 'Clean view of performance, comparison, coverage, and readiness.'
        dashboard_theme    = 'default'

    if dashboard_theme == 'newborn' and not (supply_inds or wf_inds or dq_inds):
        _unavail = {'unique': 'person_id', 'variable1': 'concept_name', 'value1': '__mnid_unavailable__'}
        wf_inds = [
            {'label': 'SSNC competency assessed', 'target_pct': 80,
             'numerator_filters': dict(_unavail), 'denominator_filters': dict(_unavail)},
        ]
        supply_inds = [
            {'label': 'CPAP equipment available', 'target_pct': 80,
             'numerator_filters': dict(_unavail), 'denominator_filters': dict(_unavail)},
            {'label': 'Phototherapy unit available', 'target_pct': 80,
             'numerator_filters': dict(_unavail), 'denominator_filters': dict(_unavail)},
            {'label': 'Neonatal resuscitation equipment available', 'target_pct': 80,
             'numerator_filters': dict(_unavail), 'denominator_filters': dict(_unavail)},
        ]
        dq_inds = [
            {'label': 'Record completeness', 'target_pct': 95,
             'numerator_filters': dict(_unavail), 'denominator_filters': dict(_unavail)},
            {'label': 'Data entered within 7 days', 'target_pct': 90,
             'numerator_filters': dict(_unavail), 'denominator_filters': dict(_unavail)},
        ]

    hero_title = (
        'KEY NEONATAL INDICATORS'
        if dashboard_theme == 'newborn'
        else f'KEY {_CAT_LABELS.get(default_cat, str(default_cat or "Program")).upper()} INDICATORS'
    )

    if not include_content:
        return {
            'indicator_content': None,
            'facility_df': facility_df,
            'network_df': network_df,
            'supply_inds': supply_inds,
            'wf_inds': wf_inds,
            'dq_inds': dq_inds,
            'dashboard_theme': dashboard_theme,
        }

    _t0 = _time.monotonic()

    _agg = _get_aggregate()
    _fac_filter  = selected_facility_codes or None
    _dist_filter = selected_districts or None
    _kpi_grain   = 'monthly'
    _coverage_grain = _aggregate_grain_for_window(_s, _e)
    _kpi_fallbacks  = list(_agg_candidate_grains(_kpi_grain))

    try:
        window    = max((_e - _s).days, 1) if _s and _e else 1
        prev_end   = _s - pd.Timedelta(days=1)
        prev_start = prev_end - pd.Timedelta(days=window - 1)
    except Exception:
        prev_start = prev_end = None

    _prev_df_filtered = pd.DataFrame()
    if prev_start is not None and prev_end is not None and 'Date' in network_df.columns and not network_df.empty:
        _prev_df_filtered = network_df[
            (network_df['Date'] >= prev_start) & (network_df['Date'] <= prev_end)
        ]
        if selected_facilities and 'Facility' in _prev_df_filtered.columns:
            _prev_df_filtered = _prev_df_filtered[_prev_df_filtered['Facility'].isin(selected_facilities)]
        elif selected_districts and 'District' in _prev_df_filtered.columns:
            _prev_df_filtered = _prev_df_filtered[_prev_df_filtered['District'].isin(selected_districts)]

    _cur_batch: dict = {}
    _prev_batch: dict = {}
    if _agg is not None and _s is not None:
        _LOGGER.info('MNID KPI source: aggregate parquet (%d rows), %d indicators', len(_agg), len(tracked))
        _cur_batch  = _build_agg_batch(_agg, _s, _e, _kpi_grain, _fac_filter,
                                        _dist_filter if not _fac_filter else None)
        if prev_start is not None:
            _prev_batch = _build_agg_batch(_agg, prev_start, prev_end, _kpi_grain, _fac_filter,
                                            _dist_filter if not _fac_filter else None)
    else:
        _LOGGER.warning('MNID KPI source: raw rows (agg=%s, start=%s)', _agg is not None, _s)
    _LOGGER.info('MNID timing: KPI batch %.2fs', _time.monotonic() - _t0)

    _cov_agg: pd.DataFrame | None = None
    if _agg is not None and _s is not None:
        _cov_grains = _agg_candidate_grains(_coverage_grain)
        _cov_floor  = min(_agg_floor_period(_s, g) for g in _cov_grains)
        _cov_agg    = _agg[
            _agg['grain'].isin(_cov_grains)
            & (_agg['period_start'] >= _cov_floor)
            & (_agg['period_start'] <= pd.Timestamp(_e))
        ]
        if _fac_filter:
            _cov_agg = _cov_agg[_cov_agg['facility_code'].isin([str(f) for f in _fac_filter])]
        elif _dist_filter:
            _cov_agg = _cov_agg[_cov_agg['district'].isin([str(d) for d in _dist_filter])]

    def _compute_inds(inds):
        computed = []
        for ind in inds:
            if _cur_batch:
                num, den, pct = _batch_cov(_cur_batch, ind['id'], _kpi_fallbacks)
                if den == 0:
                    num, den, pct = _cov(facility_df, ind['numerator_filters'], ind['denominator_filters'])
            elif _agg is not None and _s is not None:
                num, den, pct = _agg_coverage(
                    _agg, ind['id'], _s, _e,
                    facility_codes=_fac_filter,
                    districts=_dist_filter if not _fac_filter else None,
                    grain=_kpi_grain, indicator_label=ind.get('label'),
                )
            else:
                num, den, pct = _cov(facility_df, ind['numerator_filters'], ind['denominator_filters'])
            computed.append({**ind, 'pct': pct, 'numerator': num, 'denominator': den,
                              'attained_pct': _target_attainment_pct(pct, ind.get('target', 0), ind)})
        return computed

    def _add_delta(computed_list):
        for c in computed_list:
            if _prev_batch and prev_start is not None:
                _, prev_den, prev_pct = _batch_cov(_prev_batch, c['id'], _kpi_fallbacks)
                if prev_den == 0:
                    try:
                        _, _, prev_pct = _cov(_prev_df_filtered, c['numerator_filters'], c['denominator_filters'])
                    except Exception:
                        prev_pct = c['pct']
                c['delta_pct'] = round(c['pct'] - prev_pct, 1)
            elif _agg is not None and prev_start is not None:
                try:
                    _, _, prev_pct = _agg_coverage(
                        _agg, c['id'], prev_start, prev_end,
                        facility_codes=_fac_filter,
                        districts=_dist_filter if not _fac_filter else None,
                        grain=_kpi_grain, indicator_label=c.get('label'),
                    )
                    c['delta_pct'] = round(c['pct'] - prev_pct, 1)
                except Exception:
                    c['delta_pct'] = None
            elif prev_start is not None:
                try:
                    _, _, prev_pct = _cov(_prev_df_filtered, c['numerator_filters'], c['denominator_filters'])
                    c['delta_pct'] = round(c['pct'] - prev_pct, 1)
                except Exception:
                    c['delta_pct'] = None
            else:
                c['delta_pct'] = None

    computed = _compute_inds(tracked)
    _add_delta(computed)
    overview_computed = _compute_inds(overview_inds)
    _add_delta(overview_computed)

    below  = [(c['label'], c['pct']) for c in computed if not _on_target(c['pct'], c['target'], c)]
    strong = [c['label'] for c in computed if _on_target(c['pct'], c['target'], c)]

    coverage_hidden_labels = {
        'Birth weight recorded', 'Vitamin K given', 'Thermal care recorded',
        'Resuscitation intervention recorded', 'KMC support recorded', 'Low birthweight newborns',
    }
    by_cat = {}
    for ind in display_inds:
        if ind.get('category') == 'Newborn' and ind.get('label') in coverage_hidden_labels:
            continue
        by_cat.setdefault(ind.get('category', 'Other'), []).append(ind)

    _t1 = _time.monotonic()
    coverage_charts = _coverage_charts_section(
        by_cat, facility_df, category_order,
        agg_df=_cov_agg if _cov_agg is not None else _agg,
        start_date=str(_s.date()) if _s is not None else start_date,
        end_date=str(_e.date()) if _e is not None else end_date,
        facility_codes=list(_fac_filter) if _fac_filter else None,
        districts=list(_dist_filter) if _dist_filter and not _fac_filter else None,
        grain=_coverage_grain,
    )
    _LOGGER.info('MNID timing: coverage_charts %.2fs', _time.monotonic() - _t1)

    from mnid.views.trends import _trend_switcher
    _t2 = _time.monotonic()
    trend_switcher = _trend_switcher(facility_df, display_inds, scope_meta=scope_meta, payload_key=payload_key)
    _LOGGER.info('MNID timing: trend_switcher %.2fs', _time.monotonic() - _t2)

    _t3 = _time.monotonic()
    performance_div, heatmap_div = _coverage_heatmap_section(
        display_inds, facility_code, network_df,
        precomputed_store=_resolve_heatmap_store(
            network_df, display_inds, facility_code, scope_meta, payload_key,
        ),
    )
    _LOGGER.info('MNID timing: heatmap_section %.2fs', _time.monotonic() - _t3)

    _t4 = _time.monotonic()
    comparative_div = _comparative_analysis_section(
        all_inds, facility_code, facility_df, payload_key=payload_key,
    )
    _LOGGER.info('MNID timing: comparative %.2fs', _time.monotonic() - _t4)

    _activity_stats = []
    if facility_df is not None and not facility_df.empty:
        try:
            computed_by_label = {
                str(item.get('label', '')): item
                for item in (computed + overview_computed)
            }

            def _indicator_activity(label: str, override_label: str | None = None, summary: str | None = None):
                item = computed_by_label.get(label)
                if not item:
                    return None
                out = dict(item)
                out['label'] = override_label or item['label']
                out['summary'] = summary or f"{int(item.get('numerator', 0)):,} of {int(item.get('denominator', 0)):,}"
                return out

            is_all_programmes = selected_program == 'All' and len(category_order) > 1

            if is_all_programmes:
                _activity_stats = [
                    _indicator_activity('ANC Complications'),
                    _indicator_activity('Labour Complications'),
                    _indicator_activity('Live Births'),
                    _indicator_activity('Maternal Deaths'),
                    _indicator_activity('Stillbirths'),
                ]
            elif default_cat == 'Labour':
                _activity_stats = [
                    _indicator_activity('Labour & Delivery Visits'),
                    _indicator_activity('Labour Complications'),
                    _indicator_activity('Partograph use'),
                    _indicator_activity('Overall caesarean section rate'),
                    _indicator_activity('Labour Clients Not Admissioned to PNC'),
                ]
            elif default_cat == 'PNC':
                _activity_stats = [
                    _indicator_activity('PNC Visits'),
                    _indicator_activity('Mother Complications'),
                    _indicator_activity('Newborn Complications'),
                    _indicator_activity('Maternal Deaths'),
                    _indicator_activity('Newborn Deaths'),
                ]
            elif default_cat == 'Newborn':
                _activity_stats = [
                    _indicator_activity('Outborn babies'),
                    _indicator_activity('Neonatal Complications at Birth'),
                    _indicator_activity('Birth asphyxia among newborn admissions'),
                    _indicator_activity('iKMC Initiated'),
                ]
            else:
                _activity_stats = [
                    _indicator_activity('ANC Visits'),
                    _indicator_activity('ANC Complications'),
                    _indicator_activity('Blood pressure measured'),
                    _indicator_activity('Tested for HIV'),
                    _indicator_activity('ANC Clients Not Admissioned to Labour'),
                ]
            _activity_stats = [item for item in _activity_stats if item]
        except Exception:
            _activity_stats = []

    def _sec_header(title, count=None, desc=None, eyebrow=None):
        return html.Div(
            className=f'mnid-section-header{" mnid-section-header-newborn" if dashboard_theme == "newborn" else ""}',
            children=[
                html.Div([
                    html.Div(eyebrow, className='mnid-section-header-eyebrow') if eyebrow else None,
                    html.Span(title, className='mnid-section-header-title'),
                    html.Div(desc, className='mnid-section-header-desc') if desc else None,
                ]),
                html.Span(f'{count} indicators' if count else '', className='mnid-section-header-count'),
            ],
        )

    indicator_content = html.Div(
        className=f'mnid-main{" mnid-main-newborn" if dashboard_theme == "newborn" else ""}',
        children=[
            _topbar(facility_code, period, len(tracked), len(awaiting),
                    facility_df=facility_df, network_df=network_df,
                    period_note=period_note, scope_meta=scope_meta,
                    title=dashboard_title, subtitle=dashboard_subtitle, theme=dashboard_theme),
            _sidebar(facility_code, theme=dashboard_theme),
            _alert_banner(below, strong),

            _section_anchor('mnid-summary'),
            _sec_header(
                'Overview',
                desc=(
                    'Neonatal program snapshot, priority indicator posture, and facility context.'
                    if dashboard_theme == 'newborn'
                    else f'{len(tracked)} available - {len(awaiting)} awaiting'
                ),
                eyebrow='Overview' if dashboard_theme == 'newborn' else None,
            ),
            _kpi_row(computed),
            _hero_donut_row(
                _activity_stats,
                preferred_cat='All' if selected_program == 'All' and len(category_order) > 1 else default_cat,
                section_title=(
                    'ALL PROGRAMME CRITICAL ACTIVITY' if selected_program == 'All' and len(category_order) > 1
                    else 'ANC PROGRAMME ACTIVITY' if default_cat == 'ANC'
                    else 'LABOUR & DELIVERY ACTIVITY' if default_cat == 'Labour'
                    else 'PNC ACTIVITY' if default_cat == 'PNC'
                    else 'NEWBORN ACTIVITY' if default_cat == 'Newborn'
                    else 'PROGRAMME ACTIVITY'
                ),
            ) if _activity_stats else None,

            _section_anchor('mnid-coverage'),
            _sec_header(
                'Coverage & Quality' if dashboard_theme == 'newborn' else 'Coverage Indicators',
                sum(len(v) for v in by_cat.values()),
                desc=(
                    'Coverage against target across the neonatal care pathway, from stabilization to follow-up.'
                    if dashboard_theme == 'newborn'
                    else 'Coverage % vs target - target threshold shown per chart'
                ),
                eyebrow='Indicators' if dashboard_theme == 'newborn' else None,
            ),
            coverage_charts,

            _section_anchor('mnid-trends'),
            _sec_header(
                'Run Charts',
                desc=(
                    'Monthly trends for neonatal admissions and outcome-related indicators, with target references where applicable.'
                    if dashboard_theme == 'newborn'
                    else '12-month rolling - dotted line = target'
                ),
                eyebrow='Trends' if dashboard_theme == 'newborn' else None,
            ),
            trend_switcher,

            _section_anchor('mnid-performance'),
            _sec_header(
                'District Performance' if dashboard_theme == 'newborn' else 'Facility Performance',
                desc=(
                    'How this newborn service compares across district and facility peers.'
                    if dashboard_theme == 'newborn'
                    else 'District comparison heatmap for key performance indicators'
                ),
                eyebrow='Performance' if dashboard_theme == 'newborn' else None,
            ),
            performance_div,

            _section_anchor('mnid-heatmap'),
            _sec_header(
                'Geographic Coverage' if dashboard_theme == 'newborn' else 'Map View',
                desc=(
                    'Geographic context for neonatal service delivery and district-level performance.'
                    if dashboard_theme == 'newborn'
                    else 'Geographic coverage map and district/facility context'
                ),
                eyebrow='Map' if dashboard_theme == 'newborn' else None,
            ),
            heatmap_div,

            _section_anchor('mnid-comparative'),
            _sec_header(
                'Facility Comparison' if dashboard_theme == 'newborn' else 'Facility & District Comparison',
                desc=(
                    'Facility and district comparison for neonatal indicators.'
                    if dashboard_theme == 'newborn'
                    else 'Cross-facility and district indicator benchmarking'
                ),
                eyebrow='Comparison' if dashboard_theme == 'newborn' else None,
            ),
            comparative_div,
        ],
    )

    return {
        'indicator_content': indicator_content,
        'facility_df': facility_df,
        'network_df': network_df,
        'supply_inds': supply_inds,
        'wf_inds': wf_inds,
        'dq_inds': dq_inds,
        'dashboard_theme': dashboard_theme,
    }


def _get_facility_df_from_state(state: dict, network_df=None):
    """Return facility_df by recomputing from network_df (cheaper than diskcache round-trip)."""
    if network_df is None:
        network_df = _get_network_df_from_state(state)
    if network_df is None:
        return None
    bundle = _build_mnid_indicator_content(
        network_df=network_df,
        config=state.get('config'),
        facility_code=state.get('facility_code'),
        start_date=state.get('start_date'),
        end_date=state.get('end_date'),
        scope_meta=state.get('scope_meta'),
        include_content=False,
    )
    return bundle.get('facility_df')


def _resolve_heatmap_store(network_df: pd.DataFrame, all_inds: list,
                           facility_code: str, scope_meta: dict | None,
                           store_key: str) -> dict:
    _, selected_facility_codes, selected_districts = _resolve_scope_filters(network_df, scope_meta or {})
    tracked = [i for i in all_inds if i.get('status') == 'tracked']
    cache_key = (
        facility_code,
        tuple(i.get('id') for i in tracked),
        tuple(sorted(selected_facility_codes)),
        tuple(sorted(selected_districts)),
        _agg_version_stamp(),
    )
    _hms_key = _dk('hms', cache_key)
    cached_hms = _MNID_EXECUTIVE_DISK_CACHE.get(_hms_key)
    if cached_hms is None:
        agg_for_heatmap = _get_aggregate()
        if agg_for_heatmap is not None and not agg_for_heatmap.empty:
            if selected_facility_codes:
                agg_for_heatmap = agg_for_heatmap[
                    agg_for_heatmap['facility_code'].isin([str(f) for f in selected_facility_codes])
                ]
            elif selected_districts:
                agg_for_heatmap = agg_for_heatmap[
                    agg_for_heatmap['district'].isin([str(d) for d in selected_districts])
                ]
            cached_hms = _compute_heatmap_store_from_agg(agg_for_heatmap, tracked, facility_code)
            # If no indicator IDs matched (stale aggregate with old IDs), fall back to raw df
            if not any(v.get('x') for v in cached_hms.get('by_facility', {}).values()):
                _LOGGER.warning(
                    'Heatmap aggregate returned no matching indicators — falling back to raw df. '
                    'Rebuild the aggregate with run_aggregation_job() to restore performance.'
                )
                cached_hms = _compute_heatmap_store(network_df, tracked, facility_code)
        else:
            cached_hms = _compute_heatmap_store(network_df, tracked, facility_code)
        if selected_districts:
            cached_hms['current_district'] = selected_districts[0]
        _MNID_EXECUTIVE_DISK_CACHE.set(_hms_key, cached_hms, expire=_MNID_UI_CACHE_TTL_SECONDS)
    return cached_hms
