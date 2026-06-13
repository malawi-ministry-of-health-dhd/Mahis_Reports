"""
MNID aggregate store.

Loads the pre-built indicator_aggregates.parquet into memory once and exposes
query helpers used by the dashboard callbacks.  All queries are simple pandas
filter operations on a small (~500K row) DataFrame — microseconds vs. the
seconds-long raw-row scans they replace.
"""
import logging
from pathlib import Path

import pandas as pd

_LOG = logging.getLogger(__name__)

_DEFAULT_OUT_DIR = 'data/mnid_aggregates'
_PARQUET_NAME    = 'indicator_aggregates.parquet'

# Module-level in-memory cache — loaded once, invalidated after overnight rebuild.
_AGG_DF: pd.DataFrame | None = None
_LOADED = False


def load_aggregate(output_dir: str = _DEFAULT_OUT_DIR) -> pd.DataFrame | None:
    """Read the aggregate parquet from disk into memory. Returns None if absent."""
    global _AGG_DF, _LOADED
    if _LOADED:
        return _AGG_DF

    path = Path(output_dir) / _PARQUET_NAME
    if not path.exists():
        _LOG.debug('Aggregate not found at %s — falling back to live compute', path)
        _LOADED = True
        _AGG_DF = None
        return None

    try:
        _AGG_DF = pd.read_parquet(str(path))
        _AGG_DF['period_start'] = pd.to_datetime(_AGG_DF['period_start'])
        _LOADED = True
        _LOG.info('Aggregate loaded: %d rows from %s', len(_AGG_DF), path)
        return _AGG_DF
    except Exception as exc:
        _LOG.warning('Failed to load aggregate parquet: %s', exc)
        _LOADED = True
        _AGG_DF = None
        return None


def get_aggregate(output_dir: str = _DEFAULT_OUT_DIR) -> pd.DataFrame | None:
    """Return the in-memory aggregate, loading it on first call."""
    global _LOADED
    if not _LOADED:
        load_aggregate(output_dir)
    return _AGG_DF


def invalidate_cache() -> None:
    """Force the next get_aggregate() call to reload from disk."""
    global _AGG_DF, _LOADED
    _AGG_DF = None
    _LOADED = False
    _LOG.info('Aggregate cache invalidated')


# ── Query helpers ─────────────────────────────────────────────────────────────

_GRAIN_PERIOD_CODE = {'daily': 'D', 'weekly': 'W', 'monthly': 'M'}
_GRAIN_FALLBACKS = {
    'daily': ['daily', 'weekly', 'monthly'],
    'weekly': ['weekly', 'monthly'],
    'monthly': ['monthly'],
}


def _floor_to_period(ts, grain: str) -> pd.Timestamp:
    """Floor a timestamp to the start of its containing period for the given grain."""
    code = _GRAIN_PERIOD_CODE.get(grain, 'M')
    return pd.Timestamp(ts).to_period(code).start_time


def _candidate_grains(grain: str) -> list[str]:
    return _GRAIN_FALLBACKS.get(str(grain or '').strip().lower(), [grain or 'monthly'])


def resolve_indicator_id(
    agg_df: pd.DataFrame,
    indicator_id: str,
    indicator_label: str | None = None,
) -> str:
    """
    Return an aggregate-backed indicator ID.

    Some runtime MNID views now synthesize fallback/program-based indicator IDs
    that differ from older IDs stored in the aggregate parquet. Prefer the
    requested ID when present, otherwise fall back to a label match.
    """
    if agg_df is None or agg_df.empty:
        return indicator_id

    requested_id = str(indicator_id or '').strip()
    if requested_id and agg_df['indicator_id'].astype(str).eq(requested_id).any():
        return requested_id

    wanted_label = str(indicator_label or '').strip()
    if not wanted_label:
        return requested_id

    label_mask = agg_df['indicator_label'].fillna('').astype(str).str.strip().eq(wanted_label)
    matches = agg_df.loc[label_mask, 'indicator_id'].dropna().astype(str)
    if matches.empty:
        return requested_id
    return matches.iloc[0]


def query_coverage(
    agg_df: pd.DataFrame,
    indicator_id: str,
    start_date,
    end_date,
    facility_codes: list[str] | None = None,
    districts: list[str] | None = None,
    grain: str = 'monthly',
    indicator_label: str | None = None,
) -> tuple[int, int, float]:
    """
    Return (numerator, denominator, pct) summed over the date window.

    start_date is floored to the period boundary so that, e.g., querying
    grain='monthly' for today always finds the current month's record even
    when today is not the first of the month.
    """
    resolved_indicator_id = resolve_indicator_id(agg_df, indicator_id, indicator_label)
    sub = pd.DataFrame()
    for candidate_grain in _candidate_grains(grain):
        period_floor = _floor_to_period(start_date, candidate_grain)
        mask = (
            (agg_df['indicator_id'] == resolved_indicator_id)
            & (agg_df['grain'] == candidate_grain)
            & (agg_df['period_start'] >= period_floor)
            & (agg_df['period_start'] <= pd.Timestamp(end_date))
        )
        if facility_codes:
            mask &= agg_df['facility_code'].isin([str(f) for f in facility_codes])
        elif districts:
            mask &= agg_df['district'].isin([str(d) for d in districts])
        sub = agg_df[mask]
        if not sub.empty:
            break
    if sub.empty:
        return 0, 0, 0.0

    num = int(sub['numerator'].sum())
    den = int(sub['denominator'].sum())
    pct = round(min(num / den * 100, 100.0), 1) if den > 0 else 0.0
    return num, den, pct


def query_time_series(
    agg_df: pd.DataFrame,
    indicator_id: str,
    grain: str = 'monthly',
    facility_codes: list[str] | None = None,
    districts: list[str] | None = None,
    start_date=None,
    end_date=None,
    indicator_label: str | None = None,
) -> pd.DataFrame:
    """
    Return a period-by-period coverage DataFrame with columns:
        period_start (datetime), numerator (int), denominator (int), pct (float)
    Summed across facilities when multiple are selected.

    start_date is floored to the period boundary so narrow ranges (e.g. today)
    still find the enclosing period's record.
    """
    resolved_indicator_id = resolve_indicator_id(agg_df, indicator_id, indicator_label)
    sub = pd.DataFrame()
    for candidate_grain in _candidate_grains(grain):
        mask = (agg_df['indicator_id'] == resolved_indicator_id) & (agg_df['grain'] == candidate_grain)

        if facility_codes:
            mask &= agg_df['facility_code'].isin([str(f) for f in facility_codes])
        elif districts:
            mask &= agg_df['district'].isin([str(d) for d in districts])

        if start_date is not None:
            mask &= agg_df['period_start'] >= _floor_to_period(start_date, candidate_grain)
        if end_date is not None:
            mask &= agg_df['period_start'] <= pd.Timestamp(end_date)

        sub = agg_df[mask]
        if not sub.empty:
            break
    if sub.empty:
        return pd.DataFrame(columns=['period_start', 'numerator', 'denominator', 'pct'])

    grouped = (
        sub.groupby('period_start')[['numerator', 'denominator']]
        .sum()
        .reset_index()
    )
    grouped['pct'] = grouped.apply(
        lambda r: round(min(r['numerator'] / r['denominator'] * 100, 100.0), 1)
        if r['denominator'] > 0 else None,
        axis=1,
    )
    return grouped.sort_values('period_start').reset_index(drop=True)
