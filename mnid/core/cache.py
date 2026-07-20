"""Shared cache state: diskcache, in-memory dicts, key helpers, scope resolution."""
import diskcache
import hashlib
import logging
import os
import pickle
import threading

import pandas as pd
from pathlib import Path

from mnid.core.constants import FACILITY_NAMES as _FACILITY_NAMES

_LOGGER = logging.getLogger(__name__)


_MNID_UI_CACHE_MAX = 16
_MNID_UI_CACHE_TTL_SECONDS = 3600

_EXECUTIVE_CACHE_DIR = os.environ.get('MNID_EXEC_CACHE_DIR') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '.mnid_exec_cache'
)
_MNID_EXECUTIVE_DISK_CACHE = diskcache.Cache(_EXECUTIVE_CACHE_DIR, size_limit=512 * 1024 * 1024)
_MNID_WARNED_MESSAGES: set = set()
_COUNTRY_PROFILE_RENDER_VERSION = "country-profile-v7-complication-rates"
_EXECUTIVE_RENDER_VERSION = "executive-v2-operational-readiness-traffic-lights"


_network_df_cache: dict = {}
_NETWORK_DF_CACHE_MAX = 6

_worker_view_cache: dict = {}
_WORKER_VIEW_CACHE_MAX = 32


def _dk(prefix: str, key_data) -> str:
    """Stable cross-process diskcache key (hash() is randomised per-process)."""
    return f'{prefix}:{hashlib.md5(pickle.dumps(key_data, protocol=4)).hexdigest()}'


def _trim_cache(cache: dict, max_entries: int) -> None:
    while len(cache) > max_entries:
        try:
            cache.pop(next(iter(cache)))
        except Exception:
            break


def _agg_version_stamp(route: str = 'default') -> str:
    """Return a string that changes whenever route's aggregate parquet is rebuilt."""
    try:
        import json as _json
        meta_path = Path(os.getcwd()) / 'data' / 'mnid_aggregates' / route / 'meta.json'
        if meta_path.exists():
            meta = _json.loads(meta_path.read_text(encoding='utf-8'))
            return str(meta.get('generated_at', ''))
    except Exception:
        pass
    return ''


def _executive_view_cache_key(selected: str, state: dict,
                              scope_meta: dict | None = None,
                              config: dict | None = None) -> tuple:
    effective_scope = scope_meta or state.get('scope_meta') or {}
    effective_config = config or state.get('config') or {}
    route = state.get('route') or (effective_scope or {}).get('route', 'default')
    return (
        selected,
        effective_config.get('report_name'),
        state.get('facility_code'),
        state.get('start_date'),
        state.get('end_date'),
        state.get('opd_key'),
        tuple(sorted((effective_scope or {}).get('selected_facilities') or [])),
        tuple(sorted((effective_scope or {}).get('selected_districts') or [])),
        tuple(sorted((effective_scope or {}).get('mnid_categories') or [])),
        (effective_scope or {}).get('dataset_version'),
        _agg_version_stamp(route),
        _EXECUTIVE_RENDER_VERSION,
    )


def _country_profile_cache_key(scope_meta, opd_key, start_date, end_date, report_name,
                                selected_facilities=(), selected_districts=()):
    route = (scope_meta or {}).get('route', 'default')
    return (
        (
            (scope_meta or {}).get('dataset_version'),
            opd_key,
            tuple(sorted(selected_facilities or ())),
            tuple(sorted(selected_districts or ())),
        ),
        start_date,
        end_date,
        report_name,
        _agg_version_stamp(route),
        _COUNTRY_PROFILE_RENDER_VERSION,
    )


def _load_dashboard_tab_config() -> dict:
    root = Path(os.getcwd())
    config_path = root / 'data' / 'visualizations' / 'dashboard_tabs_config.json'
    raw = {}
    try:
        if config_path.exists():
            import json as _json
            raw = _json.loads(config_path.read_text(encoding='utf-8')) or {}
    except Exception:
        raw = {}

    hidden = raw.get('hidden_mnid_tabs')
    if not isinstance(hidden, list):
        hidden = []
    mnh_tabs = raw.get('mnh_tabs')
    if not isinstance(mnh_tabs, list):
        mnh_tabs = []
    normalized_tabs = []
    for item in mnh_tabs:
        if not isinstance(item, dict):
            continue
        tab_id = str(item.get('id') or '').strip()
        label = str(item.get('label') or tab_id).strip()
        if not tab_id or not label:
            continue
        normalized_tabs.append({
            'id': tab_id,
            'label': label,
            'module': str(item.get('module') or '').strip() or None,
            'placeholder': bool(item.get('placeholder')),
        })
    return {
        'hidden_mnid_tabs': {str(item).strip() for item in hidden if str(item).strip()},
        'mnh_tabs': normalized_tabs,
    }


def _resolve_scope_filters(df: pd.DataFrame, scope_meta: dict | None = None) -> tuple[list[str], list[str], list[str]]:
    """Split scope into facility names, facility codes, and districts."""
    scope_meta = scope_meta or {}
    selected_facilities = [
        str(value).strip() for value in (scope_meta.get('selected_facilities') or [])
        if str(value).strip()
    ]
    selected_districts = [
        str(value).strip() for value in (scope_meta.get('selected_districts') or [])
        if str(value).strip()
    ]
    selected_facility_codes: list[str] = []

    if df is not None and not df.empty and 'Facility_CODE' in df.columns:
        code_series = df['Facility_CODE'].dropna().astype(str).str.strip()
        known_codes = set(code_series[code_series.ne('')].unique().tolist())

        if selected_facilities:
            direct_codes = [value for value in selected_facilities if value in known_codes]
            selected_facility_codes.extend(direct_codes)

            if 'Facility' in df.columns:
                fac_meta = (
                    df[['Facility', 'Facility_CODE']]
                    .dropna(subset=['Facility', 'Facility_CODE'])
                    .assign(
                        Facility=lambda x: x['Facility'].astype(str).str.strip(),
                        Facility_CODE=lambda x: x['Facility_CODE'].astype(str).str.strip(),
                    )
                )
                name_to_codes: dict[str, list[str]] = {}
                for facility_name, facility_code in fac_meta.itertuples(index=False):
                    if not facility_name or not facility_code:
                        continue
                    name_to_codes.setdefault(facility_name, [])
                    if facility_code not in name_to_codes[facility_name]:
                        name_to_codes[facility_name].append(facility_code)
                for facility_name in selected_facilities:
                    selected_facility_codes.extend(name_to_codes.get(facility_name, []))

        selected_facility_codes = list(dict.fromkeys(selected_facility_codes))

    return selected_facilities, selected_facility_codes, selected_districts


def _get_network_df_from_state(state: dict):
    """Return network_df: check per-worker cache first, then shared diskcache."""
    opd_key = state.get('opd_key')
    if opd_key is None:
        return None
    if opd_key in _network_df_cache:
        return _network_df_cache[opd_key]
    ndf = _MNID_EXECUTIVE_DISK_CACHE.get(_dk('ndf', opd_key))
    if ndf is not None:
        _network_df_cache[opd_key] = ndf
        _trim_cache(_network_df_cache, _NETWORK_DF_CACHE_MAX)
    return ndf


def clear_runtime_caches() -> None:
    from mnid.core.data_utils import _MNID_UI_CACHE
    _network_df_cache.clear()
    _worker_view_cache.clear()
    _MNID_UI_CACHE.clear()
    try:
        _MNID_EXECUTIVE_DISK_CACHE.clear()
    except Exception:
        pass
    from mnid.aggregation.store import invalidate_cache as _agg_invalidate
    _agg_invalidate()


def _maybe_build_aggregate_on_startup(route: str = 'default') -> None:
    """Build the indicator aggregate parquet for one route in a background thread at startup.

    Only the eagerly-warmed route (today, just 'default') needs this — any
    other route gets its aggregate lazily on first request, triggered from
    mnid.aggregation.store.load_aggregate() instead.
    """
    _out_dir = Path('data') / 'mnid_aggregates' / route
    _agg_path = _out_dir / 'indicator_aggregates.parquet'
    _lock_path = _out_dir / '.agg_running'
    _source_path = Path('data') / route / 'parquet'

    if _agg_path.exists():
        return
    if not _source_path.exists():
        _LOGGER.info(
            'Startup aggregation skipped for route=%s; data source is not available: %s',
            route,
            _source_path,
        )
        return

    def _build():
        import time as _time
        _time.sleep(15)
        try:
            if _lock_path.exists():
                import datetime as _dt
                age = _dt.datetime.utcnow().timestamp() - _lock_path.stat().st_mtime
                if not (0 <= age < 3600):
                    _lock_path.unlink(missing_ok=True)
                    _LOGGER.info('Cleared stale aggregation lock before startup build (route=%s).', route)
        except Exception:
            pass
        try:
            from mnid.aggregation.scheduler import run_aggregation_job
            _LOGGER.info('Aggregate parquet not found for route=%s, building monthly grain in background...', route)
            ok = run_aggregation_job(grains=['monthly'], route=route)
            if ok:
                _LOGGER.info('Startup aggregation complete for route=%s (monthly grain).', route)
            else:
                _LOGGER.warning('Startup aggregation returned False for route=%s, check data source and indicators.', route)
        except Exception as _exc:
            _LOGGER.warning('Startup aggregation failed for route=%s: %s', route, _exc)

    t = threading.Thread(target=_build, daemon=True, name=f'mnid-startup-agg-{route}')
    t.start()


def _warm_worker_ndf_from_diskcache() -> None:
    """Load the most-recently-written network_df into this worker's in-memory cache."""
    def _load():
        try:
            ndf_key = _MNID_EXECUTIVE_DISK_CACHE.get('ndf:latest_key')
            opd_key = _MNID_EXECUTIVE_DISK_CACHE.get('ndf:latest_opd_key')
            if ndf_key is None or opd_key is None:
                return
            if opd_key in _network_df_cache:
                return
            ndf = _MNID_EXECUTIVE_DISK_CACHE.get(ndf_key)
            if ndf is None:
                return
            _network_df_cache[opd_key] = ndf
            _trim_cache(_network_df_cache, _NETWORK_DF_CACHE_MAX)
            _warm_route = opd_key[0] if isinstance(opd_key, tuple) and opd_key else 'default'
            from mnid.core.data_utils import register_facility_metadata as _reg
            _reg(ndf, route=_warm_route)
            _LOGGER.info('Worker ndf warm: %d rows loaded from diskcache', len(ndf))
        except Exception as exc:
            _LOGGER.debug('Worker ndf warm failed (non-fatal): %s', exc)
    threading.Thread(target=_load, daemon=True, name='mnid-worker-ndf-warm').start()


# Run warm-up at module import (happens in every Gunicorn worker).
_maybe_build_aggregate_on_startup()
_warm_worker_ndf_from_diskcache()
