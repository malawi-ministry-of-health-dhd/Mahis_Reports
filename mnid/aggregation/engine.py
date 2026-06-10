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

_DEFAULT_DATA_DIR = os.path.join('data', 'parquet')
_DEFAULT_VIZ_DIR = os.path.join('data', 'visualizations')
_DEFAULT_OUT_DIR = os.path.join('data', 'mnid_aggregates')

_GRAINS = ['monthly', 'weekly', 'daily']
_GRAIN_CODES = {'daily': 'D', 'weekly': 'W', 'monthly': 'M'}


def _load_all_indicators(viz_dir: str) -> list[dict]:
    """Extract all unique indicator configs from every dashboard JSON."""
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
    return indicators


def _aggregate_grain(prepared_df: pd.DataFrame, indicators: list[dict], grain: str) -> pd.DataFrame:
    """Compute coverage per facility × indicator × period for one time grain."""
    from mnid.chart_helpers import _cov

    if prepared_df.empty or 'Date' not in prepared_df.columns:
        return pd.DataFrame()

    code = _GRAIN_CODES[grain]
    df = prepared_df.copy()
    df['_period'] = pd.to_datetime(df['Date'], errors='coerce').dt.to_period(code)

    fac_col = 'Facility_CODE' if 'Facility_CODE' in df.columns else None
    dist_col = 'District' if 'District' in df.columns else None

    if fac_col:
        groups = [(fac, g) for fac, g in df.groupby(fac_col, sort=False)]
    else:
        groups = [('__all__', df)]

    rows: list[dict] = []
    for fac_code, fac_df in groups:
        district = str(fac_df[dist_col].iloc[0]) if dist_col and len(fac_df) else ''
        for period, period_df in fac_df.groupby('_period', sort=False):
            period_start = period.start_time.normalize()
            for ind in indicators:
                try:
                    num, den, pct = _cov(period_df, ind['numerator_filters'], ind['denominator_filters'])
                except Exception:
                    num, den, pct = 0, 0, 0.0
                rows.append({
                    'indicator_id':    ind['id'],
                    'indicator_label': ind.get('label', ''),
                    'category':        ind.get('category', ''),
                    'target':          ind.get('target', 0),
                    'facility_code':   str(fac_code),
                    'district':        district,
                    'grain':           grain,
                    'period_start':    period_start,
                    'numerator':       int(num),
                    'denominator':     int(den),
                    'pct':             float(pct),
                })

    return pd.DataFrame(rows)


def run_aggregation(
    data_dir: str = _DEFAULT_DATA_DIR,
    viz_dir: str = _DEFAULT_VIZ_DIR,
    output_dir: str = _DEFAULT_OUT_DIR,
) -> bool:
    """
    Full aggregation pipeline. Returns True on success.
    Typically called overnight after data_storage.py refreshes the parquet files.
    """
    from mnid.data_utils import prepare_mnid_dataframe as _prepare

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    parquet_out = out / 'indicator_aggregates.parquet'
    meta_out    = out / 'meta.json'

    _LOG.info('MNID aggregation started')
    started_at = datetime.utcnow()

    # ── 1. Load raw parquets ──────────────────────────────────────────────────
    parquet_files = sorted(glob.glob(os.path.join(data_dir, '*.parquet')))
    if not parquet_files:
        _LOG.warning('No parquet files in %s — skipping aggregation', data_dir)
        return False

    dfs = []
    for fp in parquet_files:
        try:
            dfs.append(pd.read_parquet(fp))
        except Exception as exc:
            _LOG.warning('Skipping %s: %s', fp, exc)
    if not dfs:
        return False

    raw_df = pd.concat(dfs, ignore_index=True)
    _LOG.info('Loaded %d raw rows from %d files', len(raw_df), len(dfs))

    # ── 2. Prepare (derive person-level context, clean dates, etc.) ───────────
    prepared_df = _prepare(raw_df)
    _LOG.info('Prepared dataframe: %d rows', len(prepared_df))

    # ── 3. Load indicator configs ─────────────────────────────────────────────
    indicators = _load_all_indicators(viz_dir)
    if not indicators:
        _LOG.warning('No indicators found in %s — nothing to aggregate', viz_dir)
        return False
    _LOG.info('Aggregating %d indicators across grains: %s', len(indicators), _GRAINS)

    # ── 4. Aggregate per grain ────────────────────────────────────────────────
    parts = []
    for grain in _GRAINS:
        _LOG.info('  grain=%s ...', grain)
        part = _aggregate_grain(prepared_df, indicators, grain)
        _LOG.info('  grain=%s → %d rows', grain, len(part))
        parts.append(part)

    agg_df = pd.concat(parts, ignore_index=True)
    agg_df['period_start'] = pd.to_datetime(agg_df['period_start'])

    # ── 5. Write output ───────────────────────────────────────────────────────
    agg_df.to_parquet(str(parquet_out), index=False, engine='pyarrow')

    elapsed = (datetime.utcnow() - started_at).total_seconds()
    meta = {
        'generated_at':  started_at.isoformat(),
        'elapsed_sec':   round(elapsed, 1),
        'rows':          len(agg_df),
        'indicators':    len(indicators),
        'grains':        _GRAINS,
        'parquet_files': parquet_files,
    }
    with open(meta_out, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    _LOG.info(
        'Aggregation complete: %d rows, %.0fs elapsed → %s',
        len(agg_df), elapsed, parquet_out,
    )
    return True


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    # When run directly, resolve paths relative to the project root
    _root = Path(__file__).resolve().parents[2]
    run_aggregation(
        data_dir=str(_root / 'data' / 'parquet'),
        viz_dir=str(_root / 'data' / 'visualizations'),
        output_dir=str(_root / 'data' / 'mnid_aggregates'),
    )
