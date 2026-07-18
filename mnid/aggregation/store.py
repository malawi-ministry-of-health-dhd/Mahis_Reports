"""
MNID aggregate store.

Loads the pre-built indicator_aggregates.parquet into memory once and exposes
query helpers used by the dashboard callbacks. All queries are simple pandas
filter operations on a small (~500K row) DataFrame, so they run in microseconds
instead of the seconds-long raw-row scans they replace.
"""
import logging
import threading
from pathlib import Path

import pandas as pd

_LOG = logging.getLogger(__name__)

_DEFAULT_ROUTE   = 'default'
_AGG_ROOT_DIR    = 'data/mnid_aggregates'
_PARQUET_NAME    = 'indicator_aggregates.parquet'

# in-memory cache, keyed by route, loaded once per route and invalidated after
# the overnight rebuild. A single un-keyed global here would let one route's
# aggregate leak into another's requests, so every route gets its own slot.
_AGG_DF_BY_ROUTE: dict[str, pd.DataFrame | None] = {}
_LOADED_ROUTES: set[str] = set()
_AGG_CACHE_MAX_ROUTES = 8

# routes with a background build already in flight, so a burst of requests
# for a not-yet-built route doesn't launch duplicate aggregation jobs.
_ROUTES_BUILDING: set[str] = set()


def _route_out_dir(route: str) -> str:
    return str(Path(_AGG_ROOT_DIR) / route)


def _trim_route_cache() -> None:
    while len(_AGG_DF_BY_ROUTE) > _AGG_CACHE_MAX_ROUTES:
        oldest = next(iter(_AGG_DF_BY_ROUTE))
        _AGG_DF_BY_ROUTE.pop(oldest, None)
        _LOADED_ROUTES.discard(oldest)


def _trigger_background_build(route: str) -> None:
    """Kick off an aggregation build for a route with no aggregate yet.

    Fire-and-forget: the current request still falls back to a live compute
    (get_aggregate returns None), the next one for this route gets the
    pre-aggregated fast path once the background build lands.
    """
    if route in _ROUTES_BUILDING:
        return
    _ROUTES_BUILDING.add(route)

    def _build():
        try:
            from mnid.aggregation.scheduler import run_aggregation_job
            _LOG.info('No aggregate found for route=%s, building monthly grain in background...', route)
            run_aggregation_job(grains=['monthly'], route=route)
        except Exception as exc:
            _LOG.warning('Background aggregate build failed for route=%s: %s', route, exc)
        finally:
            _ROUTES_BUILDING.discard(route)

    threading.Thread(target=_build, daemon=True, name=f'mnid-agg-build-{route}').start()


def _meta_source_matches(output_dir: str) -> bool:
    """Return False if the stored aggregate was built from a different data source."""
    import json
    try:
        from config import USE_DEMO_DATA
        meta_path = Path(output_dir) / 'meta.json'
        if not meta_path.exists():
            return True  # nothing to check against, trust the parquet
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
        agg_is_demo = bool(meta.get('use_demo_data', True))
        if agg_is_demo != bool(USE_DEMO_DATA):
            _LOG.warning(
                'Aggregate was built from %s data but app is using %s data, discarding stale aggregate.',
                'demo' if agg_is_demo else 'live',
                'demo' if USE_DEMO_DATA else 'live',
            )
            return False
    except Exception:
        pass
    return True


def load_aggregate(route: str = _DEFAULT_ROUTE, output_dir: str | None = None) -> pd.DataFrame | None:
    """Read the aggregate parquet for one route from disk into memory. Returns None if absent."""
    output_dir = output_dir or _route_out_dir(route)
    if route in _LOADED_ROUTES:
        return _AGG_DF_BY_ROUTE.get(route)

    path = Path(output_dir) / _PARQUET_NAME
    if not path.exists():
        _LOG.debug('Aggregate not found at %s (route=%s), falling back to live compute', path, route)
        _trigger_background_build(route)
        _LOADED_ROUTES.add(route)
        _AGG_DF_BY_ROUTE[route] = None
        _trim_route_cache()
        return None

    if not _meta_source_matches(output_dir):
        _LOADED_ROUTES.add(route)
        _AGG_DF_BY_ROUTE[route] = None
        _trim_route_cache()
        return None

    try:
        agg_df = pd.read_parquet(str(path))
        agg_df['period_start'] = pd.to_datetime(agg_df['period_start'])
        _AGG_DF_BY_ROUTE[route] = agg_df
        _LOADED_ROUTES.add(route)
        _trim_route_cache()
        _LOG.info('Aggregate loaded: %d rows from %s (route=%s)', len(agg_df), path, route)
        return agg_df
    except Exception as exc:
        _LOG.warning('Failed to load aggregate parquet for route=%s: %s', route, exc)
        _LOADED_ROUTES.add(route)
        _AGG_DF_BY_ROUTE[route] = None
        _trim_route_cache()
        return None


def get_aggregate(route: str = _DEFAULT_ROUTE, output_dir: str | None = None) -> pd.DataFrame | None:
    """Return the in-memory aggregate for one route, loading it on first call."""
    if route not in _LOADED_ROUTES:
        return load_aggregate(route, output_dir)
    return _AGG_DF_BY_ROUTE.get(route)


def invalidate_cache(route: str | None = None) -> None:
    """Force the next get_aggregate() call to reload from disk. route=None clears every route."""
    if route is None:
        _AGG_DF_BY_ROUTE.clear()
        _LOADED_ROUTES.clear()
        _LOG.info('Aggregate cache invalidated (all routes)')
        return
    _AGG_DF_BY_ROUTE.pop(route, None)
    _LOADED_ROUTES.discard(route)
    _LOG.info('Aggregate cache invalidated (route=%s)', route)


# query helpers

_GRAIN_PERIOD_CODE = {'daily': 'D', 'weekly': 'W', 'monthly': 'M', 'quarterly': 'Q', 'yearly': 'Y'}
_GRAIN_FALLBACKS = {
    'daily': ['daily', 'weekly', 'monthly'],
    'weekly': ['weekly', 'monthly'],
    'monthly': ['monthly'],
    'quarterly': ['quarterly', 'monthly'],
    'yearly': ['yearly', 'quarterly', 'monthly'],
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
