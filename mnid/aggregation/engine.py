"""
MNID pre-aggregation engine.

Reads all parquet data files + all indicator configs from dashboard JSONs,
computes numerator/denominator/pct per facility per period per indicator,
and writes a compact aggregate parquet to data/mnid_aggregates/.

Run overnight so the dashboard can serve period queries as fast O(1) lookups
instead of scanning 1.7M+ raw rows per request.
"""
import glob
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

_LOG = logging.getLogger(__name__)

_DEFAULT_VIZ_DIR = os.path.join('data', 'visualizations')
_DEFAULT_OUT_DIR = os.path.join('data', 'mnid_aggregates')

_GRAINS = ['monthly', 'weekly', 'daily']
_GRAIN_CODES = {'daily': 'D', 'weekly': 'W', 'monthly': 'M'}


def _load_all_indicators(viz_dir: str) -> list[dict]:
    """Extract all unique indicator configs from every dashboard JSON plus
    the hardcoded program-based indicators defined in mnid/indicators.py.

    The program-based indicators are never in any JSON file, so they must
    be added explicitly here to be covered by the pre-aggregation pass.
    """
    seen: set[str] = set()
    indicators: list[dict] = []
    for path in glob.glob(os.path.join(viz_dir, '*.json')):
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception as exc:
            _LOG.warning('Could not parse %s: %s', path, exc)
            continue

        # Handle both list-of-dashboards and single-dashboard JSON shapes
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            vt = item.get('visualization_types') or {}
            for field in ('priority_indicators',):
                for ind in (item.get(field) or vt.get(field) or []):
                    iid = ind.get('id')
                    if (
                        iid and iid not in seen
                        and ind.get('numerator_filters')
                        and ind.get('denominator_filters')
                    ):
                        seen.add(iid)
                        indicators.append(ind)

    # Add program-based indicators (ANC, Labour, PNC, Newborn) defined in
    # mnid/indicators.py — these are Python-only and have no JSON counterpart.
    try:
        from mnid.core.indicators import (
            _program_based_priority_indicators,
            _program_based_overlay_fallbacks,
        )
        for ind in _program_based_priority_indicators() + _program_based_overlay_fallbacks():
            iid = ind.get('id')
            if (
                iid and iid not in seen
                and ind.get('numerator_filters')
                and ind.get('denominator_filters')
            ):
                seen.add(iid)
                indicators.append(ind)
        _LOG.info('Loaded %d program-based indicators', sum(1 for i in indicators if str(i.get('id', '')).startswith('mnid_')))
    except Exception as exc:
        _LOG.warning('Could not load program-based indicators: %s', exc)

    return indicators


def _aggregate_grain(prepared_df: pd.DataFrame, indicators: list[dict], grain: str) -> pd.DataFrame:
    """Compute coverage per facility, indicator, and period for one time grain.

    Filters once per indicator over the whole dataframe (via _grouped_filter_counts,
    which reuses the same _apply_filter logic create_count_from_config would use per
    cell) and groups by (facility, period) in a single pass, instead of calling _cov
    once for every facility/period/indicator combination.
    """
    from mnid.charts.chart_helpers import _grouped_filter_counts

    if prepared_df.empty or 'Date' not in prepared_df.columns:
        return pd.DataFrame()

    code = _GRAIN_CODES[grain]
    df = prepared_df.copy()
    df['_period'] = pd.to_datetime(df['Date'], errors='coerce').dt.to_period(code).dt.start_time

    fac_col = 'Facility_CODE' if 'Facility_CODE' in df.columns else None
    dist_col = 'District' if 'District' in df.columns else None
    if fac_col is None:
        fac_col = '_all_facilities'
        df[fac_col] = '__all__'

    group_cols = [fac_col, '_period']
    skeleton = df.groupby(group_cols, sort=False).size().reset_index(name='_n')
    skeleton['district'] = (
        skeleton[fac_col].map(df.groupby(fac_col, sort=False)[dist_col].first()).fillna('').astype(str)
        if dist_col else ''
    )
    target_index = pd.MultiIndex.from_arrays(
        [skeleton[fac_col].values, skeleton['_period'].values], names=group_cols,
    )

    parts = []
    for ind in indicators:
        try:
            num_counts = _grouped_filter_counts(df, group_cols, ind['numerator_filters'])
            den_counts = _grouped_filter_counts(df, group_cols, ind['denominator_filters'])
        except Exception:
            num_counts = pd.Series(dtype='int64')
            den_counts = pd.Series(dtype='int64')

        part = skeleton[[fac_col, '_period', 'district']].copy()
        part['numerator'] = num_counts.reindex(target_index).fillna(0).to_numpy().astype(int)
        part['denominator'] = den_counts.reindex(target_index).fillna(0).to_numpy().astype(int)
        den_safe = part['denominator'].where(part['denominator'] > 0, 1)
        part['pct'] = (
            (part['numerator'] / den_safe * 100).clip(upper=100.0).round(1)
            .where(part['denominator'] > 0, 0.0)
        )
        part['indicator_id'] = ind['id']
        part['indicator_label'] = ind.get('label', '')
        part['category'] = ind.get('category', '')
        part['target'] = ind.get('target', 0)
        part['facility_code'] = part[fac_col].astype(str)
        part['grain'] = grain
        part['period_start'] = part['_period']
        parts.append(part[[
            'indicator_id', 'indicator_label', 'category', 'target', 'facility_code',
            'district', 'grain', 'period_start', 'numerator', 'denominator', 'pct',
        ]])

    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    out['numerator'] = out['numerator'].astype(int)
    out['denominator'] = out['denominator'].astype(int)
    out['pct'] = out['pct'].astype(float)
    return out


def run_aggregation(
    viz_dir: str = _DEFAULT_VIZ_DIR,
    output_dir: str = _DEFAULT_OUT_DIR,
    grains: list[str] | None = None,
) -> bool:
    """
    Full aggregation pipeline. Returns True on success.
    Loads data from the same source as the live app (DATA_FILE_NAME_ in config).
    Typically called overnight after data_storage.py refreshes the parquet files.
    """
    from mnid.core.data_utils import prepare_mnid_dataframe as _prepare
    from config import DATA_FILE_NAME_
    from data_storage import DataStorage

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    parquet_out = out / 'indicator_aggregates.parquet'
    meta_out    = out / 'meta.json'

    _LOG.info('MNID aggregation started')
    started_at = datetime.utcnow()

    # load raw data the same way the live app does
    _mnid_cols = ', '.join([
        'person_id', 'encounter_id', 'Date', 'Program', 'Reporting_Program',
        'Service_Area', 'Facility', 'Facility_CODE', 'District', 'Encounter',
        'obs_value_coded', 'concept_name', 'Value', 'ValueN', 'new_revisit',
        'Home_district', 'TA', 'Village', 'Age', 'Age_Group', 'Gender',
        'Source_Program',
    ])
    try:
        raw_df = DataStorage.query_duckdb(f"SELECT {_mnid_cols} FROM '{DATA_FILE_NAME_}'")
        raw_df['Date'] = pd.to_datetime(raw_df['Date'], errors='coerce')
    except Exception as exc:
        _LOG.error('Failed to load data from %s: %s', DATA_FILE_NAME_, exc)
        return False

    if raw_df.empty:
        _LOG.warning('No data in %s, skipping aggregation', DATA_FILE_NAME_)
        return False

    _LOG.info('Loaded %d raw rows from %s', len(raw_df), DATA_FILE_NAME_)

    # derive person-level context, clean dates, etc.
    prepared_df = _prepare(raw_df)
    _LOG.info('Prepared dataframe: %d rows', len(prepared_df))

    indicators = _load_all_indicators(viz_dir)
    if not indicators:
        _LOG.warning('No indicators found in %s, nothing to aggregate', viz_dir)
        return False
    active_grains = grains if grains is not None else _GRAINS
    _LOG.info('Aggregating %d indicators across grains: %s', len(indicators), active_grains)

    parts = []
    for grain in active_grains:
        _LOG.info('  grain=%s ...', grain)
        part = _aggregate_grain(prepared_df, indicators, grain)
        _LOG.info('  grain=%s: %d rows', grain, len(part))
        parts.append(part)

    agg_df = pd.concat(parts, ignore_index=True)
    agg_df['period_start'] = pd.to_datetime(agg_df['period_start'])

    agg_df.to_parquet(str(parquet_out), index=False, engine='pyarrow')

    elapsed = (datetime.utcnow() - started_at).total_seconds()
    meta = {
        'generated_at':    started_at.isoformat(),
        'elapsed_sec':     round(elapsed, 1),
        'rows':            len(agg_df),
        'indicators':      len(indicators),
        'grains':          _GRAINS,
        'data_source':     DATA_FILE_NAME_,
        'use_demo_data':   bool(DATA_FILE_NAME_ == 'demo_parquet'),
        'last_run_status': 'ok',
    }
    with open(meta_out, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    _LOG.info(
        'Aggregation complete: %d rows, %.0fs elapsed, written to %s',
        len(agg_df), elapsed, parquet_out,
    )
    return True


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    _root = Path(__file__).resolve().parents[2]
    run_aggregation(
        viz_dir=str(_root / 'data' / 'visualizations'),
        output_dir=str(_root / 'data' / 'mnid_aggregates'),
    )
