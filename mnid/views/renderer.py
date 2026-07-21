"""Dashboard renderer — render_mnid_dashboard, executive tab assembly, cache prewarming."""
import hashlib
import json
import logging
import pickle
import threading
from pathlib import Path

import pandas as pd
from dash import html, dcc, callback, Input, Output, State, MATCH
from dash.exceptions import PreventUpdate

from mnid.core.cache import (
    _dk, _trim_cache,
    _agg_version_stamp,
    _executive_view_cache_key, _country_profile_cache_key,
    _load_dashboard_tab_config,
    _get_network_df_from_state,
    _MNID_EXECUTIVE_DISK_CACHE, _MNID_UI_CACHE_TTL_SECONDS,
    _network_df_cache, _NETWORK_DF_CACHE_MAX,
    _worker_view_cache, _WORKER_VIEW_CACHE_MAX,
)
from mnid.views.kpi_engine import (
    _build_mnid_indicator_content,
    _get_facility_df_from_state,
    _load_mnid_report_config,
)
from mnid.core.data_utils import prepare_mnid_dataframe as _prepare_mnid_dataframe
from mnid.dashboards import load_dashboard_module
from mnid.views.executive_views import render_country_profile, render_operational_readiness, _profile_scope_name
from mnid.components.run_charts import (
    bucket_multi_series, bucket_time_series,
    _multi_run_chart, _run_chart, describe_grain_window,
)
from mnid.core.constants import BORDER, TEXT

_LOGGER = logging.getLogger(__name__)


def _render_mnh_placeholder(label: str) -> html.Div:
    return html.Div(
        style={
            'padding': '28px',
            'border': f'1px dashed {BORDER}',
            'borderRadius': '20px',
            'background': '#FFFFFF',
            'color': '#475569',
        },
        children=[
            html.Div(label, style={'fontSize': '12px', 'fontWeight': 800, 'textTransform': 'uppercase', 'letterSpacing': '0.08em'}),
            html.Div('This dashboard view is reserved for a future implementation.', style={'fontSize': '24px', 'fontWeight': 800, 'color': TEXT, 'marginTop': '8px'}),
            html.Div('The current release keeps the slot visible so routing and navigation are ready when MNH-Nest360 is implemented.', style={'fontSize': '13px', 'marginTop': '8px'}),
        ],
    )


def _mnid_loading_placeholder() -> html.Div:
    return html.Div(
        className='mnid-loading-surface',
        children=[
            html.Div(className='mnid-loading-surface-hero'),
            html.Div(
                className='mnid-loading-surface-grid',
                children=[
                    html.Div(className='mnid-loading-surface-card'),
                    html.Div(className='mnid-loading-surface-card'),
                    html.Div(className='mnid-loading-surface-card'),
                ],
            ),
            html.Div(className='mnid-loading-surface-wide'),
        ],
    )


def prewarm_cache(dataset_version: str | None = None, route: str = 'default') -> bool:
    """
    Pre-compute and cache the prepared MNID network DataFrame so the first
    user request hits a warm cache instead of running the 8-9s prepare step.
    Safe to call from a background thread at server startup.
    """
    try:
        from data_storage import DataStorage

        _mnid_cols = ', '.join([
            'person_id', 'encounter_id', 'Date', 'Program', 'Reporting_Program',
            'Service_Area', 'Facility', 'Facility_CODE', 'District', 'Encounter',
            'obs_value_coded', 'concept_name', 'Value', 'ValueN', 'new_revisit',
            'Home_district', 'TA', 'Village', 'Age', 'Age_Group', 'Gender',
            'Source_Program',
        ])
        full = DataStorage.query_duckdb(f"SELECT {_mnid_cols} FROM 'data/{route}/parquet'")
        full['Date'] = pd.to_datetime(full['Date'], errors='coerce')

        opd_key = (
            route,
            dataset_version,
            len(full),
            tuple(full.columns.tolist()) if not full.empty else (),
            (),
            (),
        )
        if opd_key in _network_df_cache:
            return False

        _LOGGER.info('MNID pre-warm: preparing %d rows...', len(full))
        net_df = _prepare_mnid_dataframe(full, route=route)
        _network_df_cache[opd_key] = net_df
        _trim_cache(_network_df_cache, _NETWORK_DF_CACHE_MAX)
        _LOGGER.info('MNID pre-warm complete: %d rows cached', len(net_df))
        return True
    except Exception as exc:
        _LOGGER.warning('MNID pre-warm failed: %s', exc)
        return False


def _prewarm_country_profile() -> bool:
    """
    Pre-render and cache the country profile for the default date window.
    Safe to call from a background thread after prewarm_cache() completes.
    """
    try:
        import datetime as _dt
        from helpers.date_ranges import get_relative_date_range

        config = _load_mnid_report_config('Maternal Health')
        if not config:
            try:
                config_path = Path(__file__).resolve().parents[2] / 'data' / 'visualizations' / 'validated_dashboard.json'
                dashboards  = json.loads(config_path.read_text(encoding='utf-8'))
                config      = next((d for d in dashboards if d.get('dashboard_type') == 'mnid'), None)
            except Exception:
                config = None
        if not config:
            return False

        start_date, end_date = get_relative_date_range('Last 3 Months')
        if start_date is None:
            end_date   = _dt.date.today()
            start_date = end_date.replace(day=1)

        for opd_key, net_df in list(_network_df_cache.items()):
            scope_meta = {
                'dataset_version': opd_key[0] if opd_key else None,
                'mnid_categories': config.get('mnid_categories') or ['ANC', 'Labour', 'PNC'],
            }
            bundle = _build_mnid_indicator_content(
                network_df=net_df, config=config,
                facility_code=None,
                start_date=start_date, end_date=end_date,
                scope_meta=scope_meta, include_content=False,
            )
            facility_df = bundle.get('facility_df')
            if facility_df is None or facility_df.empty:
                continue

            cp_key = _country_profile_cache_key(
                scope_meta, opd_key, start_date, end_date, config.get('report_name'),
            )
            _cp_disk_key = _dk('cp', cp_key)
            if _worker_view_cache.get(_cp_disk_key) or _MNID_EXECUTIVE_DISK_CACHE.get(_cp_disk_key):
                _LOGGER.info('MNID country-profile pre-warm: already cached')
                return False

            _LOGGER.info('MNID country-profile pre-warm: rendering...')
            country_label = 'Maternal & Newborn' if config.get('report_name') == 'Maternal Health' else 'Maternal'
            cp_view = render_country_profile(facility_df, scope_meta=scope_meta, indicator_label=country_label, start_date=start_date, end_date=end_date)
            _MNID_EXECUTIVE_DISK_CACHE.set(_cp_disk_key, cp_view, expire=_MNID_UI_CACHE_TTL_SECONDS)
            _worker_view_cache[_cp_disk_key] = cp_view
            _trim_cache(_worker_view_cache, _WORKER_VIEW_CACHE_MAX)
            _LOGGER.info('MNID country-profile pre-warm: complete')
            return True

    except Exception as exc:
        _LOGGER.warning('MNID country-profile pre-warm failed: %s', exc)
    return False


def _build_executive_tab_view(
    selected: str, views: dict, state: dict,
    scope_meta_override: dict | None = None,
    config_override: dict | None = None,
    store_in_views: bool = True,
):
    import time as _time

    config       = config_override or state.get('config')
    facility_code = state.get('facility_code')
    start_date   = state.get('start_date')
    end_date     = state.get('end_date')
    scope_meta   = scope_meta_override or state.get('scope_meta')
    supply_inds  = state.get('supply_inds')
    wf_inds      = state.get('wf_inds')
    dq_inds      = state.get('dq_inds')
    country_label = state.get('country_label') or 'Maternal'

    if selected in views:
        return views.get(selected, views.get('country-profile', html.Div()))

    view_cache_key = _executive_view_cache_key(selected, state, scope_meta=scope_meta, config=config)
    _etv_key       = _dk('etv', view_cache_key)

    # Maternal and newborn tabs hold dcc.Stores whose data_key values point into
    # _MNID_UI_CACHE (mnid/core/data_utils.py), which is now disk-backed and
    # shared across worker processes and restarts - so every tab can safely use
    # the shared disk cache, not just the worker-local one.
    _use_disk_cache = True

    cached_view = _worker_view_cache.get(_etv_key)
    if cached_view is None and _use_disk_cache:
        cached_view = _MNID_EXECUTIVE_DISK_CACHE.get(_etv_key)
        if cached_view is not None:
            _worker_view_cache[_etv_key] = cached_view
            _trim_cache(_worker_view_cache, _WORKER_VIEW_CACHE_MAX)
    if cached_view is not None:
        if store_in_views:
            views[selected] = cached_view
        return cached_view

    _etv_t0    = _time.monotonic()
    network_df = _get_network_df_from_state(state)
    _LOGGER.info('MNID tab timing: ndf fetch %.2fs (selected=%s)', _time.monotonic() - _etv_t0, selected)
    _fdf_t0    = _time.monotonic()
    facility_df = _get_facility_df_from_state(state, network_df=network_df)
    _LOGGER.info('MNID tab timing: facility_df %.2fs (selected=%s)', _time.monotonic() - _fdf_t0, selected)

    def _cache_view(view):
        _worker_view_cache[_etv_key] = view
        _trim_cache(_worker_view_cache, _WORKER_VIEW_CACHE_MAX)
        if _use_disk_cache:
            def _async_write():
                try:
                    _MNID_EXECUTIVE_DISK_CACHE.set(_etv_key, view, expire=_MNID_UI_CACHE_TTL_SECONDS)
                except Exception:
                    pass
            threading.Thread(target=_async_write, daemon=True).start()

    if selected == 'country-profile' and facility_df is not None:
        cp_key = _country_profile_cache_key(
            scope_meta, state.get('opd_key'), start_date, end_date,
            config.get('report_name') if config else None,
            (scope_meta or {}).get('selected_facilities') or (),
            (scope_meta or {}).get('selected_districts') or (),
        )
        _cp_disk_key = _dk('cp', cp_key)
        cp_cached    = _worker_view_cache.get(_cp_disk_key)
        if cp_cached is None:
            cp_cached = _MNID_EXECUTIVE_DISK_CACHE.get(_cp_disk_key)
        if cp_cached is None:
            cp_cached = render_country_profile(facility_df, scope_meta=scope_meta, indicator_label=country_label, start_date=start_date, end_date=end_date)
            _MNID_EXECUTIVE_DISK_CACHE.set(_cp_disk_key, cp_cached, expire=_MNID_UI_CACHE_TTL_SECONDS)
        _worker_view_cache[_cp_disk_key] = cp_cached
        _trim_cache(_worker_view_cache, _WORKER_VIEW_CACHE_MAX)
        views[selected] = cp_cached
        return cp_cached

    if selected == 'operational-readiness' and facility_df is not None:
        rendered_view = render_operational_readiness(
            facility_df, supply_inds=supply_inds, wf_inds=wf_inds, dq_inds=dq_inds,
        )
        if store_in_views:
            views[selected] = rendered_view
        _cache_view(rendered_view)
        return rendered_view

    if selected == 'maternal-dashboard' and network_df is not None and config is not None:
        _mat_t0 = _time.monotonic()
        bundle = _build_mnid_indicator_content(
            network_df=network_df, config=config,
            facility_code=facility_code,
            start_date=start_date, end_date=end_date,
            scope_meta=scope_meta, include_content=True,
        )
        rendered_view = bundle.get('indicator_content', html.Div())
        _LOGGER.info('MNID tab timing: maternal build %.2fs', _time.monotonic() - _mat_t0)
        if store_in_views:
            views[selected] = rendered_view
        _cache_view(rendered_view)
        return rendered_view

    if selected == 'newborn-dashboard':
        newborn_config    = state.get('newborn_config')
        newborn_scope_meta = state.get('newborn_scope_meta')
        if network_df is not None and newborn_config is not None:
            bundle = _build_mnid_indicator_content(
                network_df=network_df, config=newborn_config,
                facility_code=facility_code,
                start_date=start_date, end_date=end_date,
                scope_meta=newborn_scope_meta, include_content=True,
            )
            rendered_view = bundle.get('indicator_content', html.Div())
            if store_in_views:
                views[selected] = rendered_view
            _cache_view(rendered_view)
            return rendered_view

    return views.get('country-profile', html.Div())


def _render_beginnings_shell(initial_tab: str, hidden_mnid_tabs: set[str], newborn_config, initial_children=None, scope_meta: dict | None = None) -> html.Div:
    _tab_style = {
        'padding': '10px 18px',
        'borderRadius': '12px',
        'border': f'1px solid {BORDER}',
        'backgroundColor': '#FFFFFF',
        'color': TEXT,
    }
    _tab_active = {
        'padding': '10px 18px',
        'borderRadius': '12px',
        'border': f'1px solid {BORDER}',
        'backgroundColor': '#F0FDF4',
        'color': '#15803D',
        'fontWeight': 700,
    }
    _tab_active2 = dict(_tab_active, backgroundColor='#F8FAFC')

    _profile_tab_label = _profile_scope_name(scope_meta)['tab_label']
    tab_children = [
        dcc.Tab(label=_profile_tab_label, value='country-profile', style=_tab_style, selected_style=_tab_active),
    ]
    if 'operational-readiness' not in hidden_mnid_tabs:
        tab_children.append(
            dcc.Tab(label='Operational Readiness', value='operational-readiness', style=_tab_style, selected_style=_tab_active2)
        )
    tab_children.append(
        dcc.Tab(label='Maternal', value='maternal-dashboard', style=_tab_style, selected_style=_tab_active2)
    )
    if newborn_config is not None:
        tab_children.append(
            dcc.Tab(label='Newborn', value='newborn-dashboard', style=_tab_style, selected_style=_tab_active2)
        )

    visible_tab_values = [getattr(tab, 'value', None) for tab in tab_children]
    resolved_initial_tab = initial_tab if initial_tab in visible_tab_values else (visible_tab_values[0] if visible_tab_values else 'country-profile')

    return html.Div(
        children=[
            dcc.Tabs(
                id='mnid-executive-tabs',
                value=resolved_initial_tab,
                style={'marginBottom': '18px'},
                children=tab_children,
            ),
            html.Div(
                id='mnid-executive-content',
                className='mnid-executive-content',
                children=initial_children if initial_children is not None else [_mnid_loading_placeholder()],
            ),
        ],
    )


def _render_mnh_dashboard_view(selected_view: str, state: dict, views: dict):
    if selected_view == 'mnh-beginnings':
        if views.get('beginnings-shell') is not None:
            return views['beginnings-shell']
        hidden_mnid_tabs = _load_dashboard_tab_config().get('hidden_mnid_tabs', set())
        return _render_beginnings_shell(
            initial_tab=state.get('beginnings_initial_tab') or 'country-profile',
            hidden_mnid_tabs=hidden_mnid_tabs,
            newborn_config=state.get('newborn_config'),
            initial_children=[_mnid_loading_placeholder()],
            scope_meta=state.get('scope_meta'),
        )

    if selected_view == 'mnh-moh':
        if selected_view in views:
            return views[selected_view]
        network_df = _get_network_df_from_state(state)
        facility_df = _get_facility_df_from_state(state, network_df=network_df)
        if network_df is None or facility_df is None:
            return html.Div('Unable to load the MNH MoH dashboard data.', style={'padding': '24px', 'color': '#DC2626'})
        try:
            module = load_dashboard_module('MNH-MoH')
            rendered = module.render_mnh_moh_dashboard(
                facility_df=facility_df,
                network_df=network_df,
                maternal_config=state.get('config') or {},
                newborn_config=state.get('newborn_config'),
                start_date=state.get('start_date'),
                end_date=state.get('end_date'),
                scope_meta=state.get('scope_meta'),
            )
            views[selected_view] = rendered
            return rendered
        except Exception as exc:
            _LOGGER.exception('Failed to render MNH MoH dashboard: %s', exc)
            return html.Div(
                f'MNH-MoH failed to load: {exc}',
                style={'padding': '24px', 'color': '#DC2626', 'fontSize': '13px'},
            )

    # Generic path: load the module declared in mnh_tab_specs for this tab id
    tab_specs = state.get('mnh_tab_specs') or []
    spec = next((t for t in tab_specs if t.get('id') == selected_view), None)
    if spec and spec.get('module') and not spec.get('placeholder'):
        folder_name = spec['module'].split('/')[-1]  # e.g. "mnid/dashboards/MNH-Nest360" → "MNH-Nest360"
        if selected_view in views:
            return views[selected_view]
        network_df  = _get_network_df_from_state(state)
        facility_df = _get_facility_df_from_state(state, network_df=network_df)
        try:
            module      = load_dashboard_module(folder_name)
            render_fn   = getattr(module, (module.__all__ or [None])[0], None)
            if render_fn is None:
                raise AttributeError(f'No render function declared in __all__ for {folder_name}')
            rendered = render_fn(
                facility_df=facility_df,
                network_df=network_df,
                maternal_config=state.get('config') or {},
                newborn_config=state.get('newborn_config'),
                start_date=state.get('start_date'),
                end_date=state.get('end_date'),
                scope_meta=state.get('scope_meta'),
            )
            views[selected_view] = rendered
            return rendered
        except Exception as exc:
            _LOGGER.exception('Failed to render %s dashboard: %s', folder_name, exc)
            return html.Div(
                f'{folder_name} failed to load: {exc}',
                style={'padding': '24px', 'color': '#DC2626', 'fontSize': '13px'},
            )

    label_map = {item.get('id'): item.get('label') for item in tab_specs}
    return _render_mnh_placeholder(label_map.get(selected_view, selected_view))


_MNID_SQL_COLUMNS = "*" #kept all for now
def render_mnid_dashboard(filtered, data_opd, data_path, config, 
                          facility_code, start_date, end_date,
                          scope_meta: dict | None = None,
                          initial_tab: dict | None = None):
    
    if isinstance(filtered, str):
        source_path = Path(data_path)
        if not source_path.is_absolute():
            source_path = Path.cwd() / source_path
        if not source_path.exists():
            return html.Div(
                'The local MAHIS dataset is unavailable for this dashboard.',
                style={'padding': '24px', 'color': '#64748B'},
            )
        from data_storage import DataStorage as _DS
        filtered = _DS.query_duckdb(
            f"SELECT {_MNID_SQL_COLUMNS} FROM '{data_path}' WHERE {filtered}"
        )
        data_opd = _DS.query_duckdb(
            f"SELECT {_MNID_SQL_COLUMNS} FROM '{data_path}' WHERE {data_opd}"
        )
    route               = (scope_meta or {}).get('route', 'default')
    dataset_version     = (scope_meta or {}).get('dataset_version')
    selected_programs   = tuple(sorted((scope_meta or {}).get('mnid_categories') or []))
    selected_facilities = tuple(sorted((scope_meta or {}).get('selected_facilities') or []))
    selected_districts  = tuple(sorted((scope_meta or {}).get('selected_districts') or []))

    _opd_key = (
        route,
        dataset_version,
        len(data_opd),
        tuple(data_opd.columns.tolist()) if not data_opd.empty else (),
        selected_facilities,
        selected_districts,
    )
    if _opd_key not in _network_df_cache:
        _network_df_cache[_opd_key] = _prepare_mnid_dataframe(data_opd, route=route)
        _trim_cache(_network_df_cache, _NETWORK_DF_CACHE_MAX)
    network_df = _network_df_cache[_opd_key]

    primary_bundle  = _build_mnid_indicator_content(
        network_df=network_df, config=config,
        facility_code=facility_code,
        start_date=start_date, end_date=end_date,
        scope_meta=scope_meta, include_content=False,
    )
    facility_df     = primary_bundle['facility_df']
    dashboard_theme = primary_bundle['dashboard_theme']

    country_label      = 'Maternal'
    newborn_scope_meta = None

    if config.get('report_name') == 'Maternal Health':
        newborn_config = _load_mnid_report_config('Newborn')
        if newborn_config:
            newborn_scope_meta = dict(scope_meta or {})
            newborn_scope_meta['mnid_categories'] = newborn_config.get('mnid_categories') or ['Newborn']
            country_label = 'Maternal & Newborn'
    else:
        newborn_config = None

    executive_content = {}
    _tok_data         = (_opd_key, str(start_date), str(end_date), config.get('report_name'), selected_programs)
    executive_token   = hashlib.md5(pickle.dumps(_tok_data, protocol=4)).hexdigest()
    _MNID_EXECUTIVE_DISK_CACHE.set(
        f'ec:{executive_token}', executive_content, expire=_MNID_UI_CACHE_TTL_SECONDS
    )
    _MNID_EXECUTIVE_DISK_CACHE.set(
        f'ed:{executive_token}',
        {
            'opd_key':           _opd_key,
            'route':             route,
            'config':            config,
            'facility_code':     facility_code,
            'start_date':        start_date,
            'end_date':          end_date,
            'scope_meta':        scope_meta,
            'supply_inds':       primary_bundle['supply_inds'],
            'wf_inds':           primary_bundle['wf_inds'],
            'dq_inds':           primary_bundle['dq_inds'],
            'newborn_config':    newborn_config,
            'newborn_scope_meta': newborn_scope_meta,
            'country_label':     country_label,
            'beginnings_initial_tab': initial_tab if initial_tab not in {'mnh-beginnings', 'mnh-moh', 'mnh-nest360'} else 'country-profile',
            'mnh_tab_specs':     _load_dashboard_tab_config().get('mnh_tabs', []),
        },
        expire=_MNID_UI_CACHE_TTL_SECONDS,
    )

    _ndf_key = _dk('ndf', _opd_key)
    if _MNID_EXECUTIVE_DISK_CACHE.get(_ndf_key) is None:
        _ndf_snap    = network_df
        _opd_key_snap = _opd_key
        def _async_write_ndf():
            try:
                _MNID_EXECUTIVE_DISK_CACHE.set(_ndf_key, _ndf_snap, expire=_MNID_UI_CACHE_TTL_SECONDS)
                _MNID_EXECUTIVE_DISK_CACHE.set('ndf:latest_key',     _ndf_key,     expire=_MNID_UI_CACHE_TTL_SECONDS)
                _MNID_EXECUTIVE_DISK_CACHE.set('ndf:latest_opd_key', _opd_key_snap, expire=_MNID_UI_CACHE_TTL_SECONDS)
            except Exception:
                pass
        threading.Thread(target=_async_write_ndf, daemon=True).start()

    _target_tab = initial_tab if initial_tab in {'country-profile', 'operational-readiness', 'maternal-dashboard', 'newborn-dashboard'} else 'country-profile'
    if _target_tab == 'country-profile':
        _cp_disk_key = _dk('cp', _country_profile_cache_key(
            scope_meta, _opd_key, start_date, end_date, config.get('report_name'),
        ))
        cp_cached = _MNID_EXECUTIVE_DISK_CACHE.get(_cp_disk_key)
        if cp_cached is None:
            cp_cached = render_country_profile(facility_df, scope_meta=scope_meta, indicator_label=country_label, start_date=start_date, end_date=end_date)
            _MNID_EXECUTIVE_DISK_CACHE.set(_cp_disk_key, cp_cached, expire=_MNID_UI_CACHE_TTL_SECONDS)
        executive_content['country-profile'] = cp_cached
        _initial_ec = [executive_content['country-profile']]
    else:
        _initial_ec = [_mnid_loading_placeholder()]

    executive_content['beginnings-shell'] = _render_beginnings_shell(
        initial_tab=_target_tab,
        hidden_mnid_tabs=_load_dashboard_tab_config().get('hidden_mnid_tabs', set()),
        newborn_config=newborn_config,
        initial_children=_initial_ec,
        scope_meta=scope_meta,
    )

    mnh_tab_specs = _load_dashboard_tab_config().get('mnh_tabs', [])
    render_as_mnh_switcher = config.get('report_name') == 'Maternal Health' and bool(mnh_tab_specs)
    outer_tab_style = {'padding': '12px 18px', 'borderRadius': '14px', 'border': f'1px solid {BORDER}', 'backgroundColor': '#FFFFFF', 'color': TEXT}
    outer_active_style = {'padding': '12px 18px', 'borderRadius': '14px', 'border': f'1px solid {BORDER}', 'backgroundColor': '#ECFDF5', 'color': '#166534', 'fontWeight': 700}

    if render_as_mnh_switcher:
        outer_values = [item.get('id') for item in mnh_tab_specs if item.get('id')]
        resolved_view = initial_tab if initial_tab in outer_values else 'mnh-beginnings'
        initial_view = (
            _render_mnh_dashboard_view(
                resolved_view,
                _MNID_EXECUTIVE_DISK_CACHE.get(f'ed:{executive_token}') or {},
                executive_content,
            )
            if resolved_view != 'mnh-beginnings' else html.Div()
        )
        _MNID_EXECUTIVE_DISK_CACHE.set(f'ec:{executive_token}', executive_content, expire=_MNID_UI_CACHE_TTL_SECONDS)
        return html.Div(
            className=f'mnid-bg{" mnid-theme-newborn" if dashboard_theme == "newborn" else ""}',
            children=[
                dcc.Store(id='mnid-executive-view-store', data=executive_token),
                dcc.Store(id='mnid-preload-status'),
                html.Div(
                    className=f'mnid-shell{" mnid-shell-newborn" if dashboard_theme == "newborn" else ""}',
                    children=[
                        dcc.Tabs(
                            id='mnid-mnh-view-tabs',
                            value=resolved_view,
                            style={'marginBottom': '18px'},
                            children=[
                                dcc.Tab(label=item.get('label'), value=item.get('id'), style=outer_tab_style, selected_style=outer_active_style)
                                for item in mnh_tab_specs
                            ],
                        ),

                        html.Div(
                            id='mnid-beginnings-panel',
                            children=[executive_content['beginnings-shell']],
                            style={} if resolved_view == 'mnh-beginnings' else {'display': 'none'},
                        ),
                        html.Div(
                            id='mnid-mnh-view-content',
                            className='mnid-executive-content',
                            children=[initial_view],
                            style={} if resolved_view != 'mnh-beginnings' else {'display': 'none'},
                        ),
                    ],
                ),
                dcc.Interval(id='mnid-background-preload', interval=3000, n_intervals=0, max_intervals=1),
            ],
        )

    return html.Div(
        className=f'mnid-bg{" mnid-theme-newborn" if dashboard_theme == "newborn" else ""}',
        children=[
            dcc.Store(id='mnid-executive-view-store', data=executive_token),
            dcc.Store(id='mnid-preload-status'),
            html.Div(
                className=f'mnid-shell{" mnid-shell-newborn" if dashboard_theme == "newborn" else ""}',
                children=[
                    executive_content['beginnings-shell'],
                ],
            ),
            dcc.Interval(id='mnid-background-preload', interval=3000, n_intervals=0, max_intervals=1),
        ],
    )


@callback(
    Output('mnid-executive-content', 'children'),
    Input('mnid-executive-tabs', 'value'),
    State('mnid-executive-view-store', 'data'),
    prevent_initial_call=False,
)
def _render_mnid_executive_tab(active_tab, executive_token):
    views    = _MNID_EXECUTIVE_DISK_CACHE.get(f'ec:{executive_token}') or {}
    selected = active_tab or 'country-profile'
    state    = _MNID_EXECUTIVE_DISK_CACHE.get(f'ed:{executive_token}') or {}

    try:
        result = _build_executive_tab_view(selected, views, state)
        _MNID_EXECUTIVE_DISK_CACHE.set(f'ec:{executive_token}', views, expire=_MNID_UI_CACHE_TTL_SECONDS)
        return result
    except Exception as _exc:
        _LOGGER.exception('Failed to render executive tab %s: %s', selected, _exc)
        return html.Div(
            f'Tab failed to load ({selected}): {_exc}',
            style={'padding': '24px', 'color': '#dc2626', 'fontSize': '13px'},
        )


@callback(
    Output('mnid-mnh-view-content', 'children'),
    Output('mnid-beginnings-panel', 'style'),
    Output('mnid-mnh-view-content', 'style'),
    Input('mnid-mnh-view-tabs', 'value'),
    State('mnid-executive-view-store', 'data'),
    prevent_initial_call=False,
)
def _render_mnh_dashboard_tab(active_tab, executive_token):
    if not executive_token:
        raise PreventUpdate

    views = _MNID_EXECUTIVE_DISK_CACHE.get(f'ec:{executive_token}') or {}
    state = _MNID_EXECUTIVE_DISK_CACHE.get(f'ed:{executive_token}') or {}
    selected = active_tab or 'mnh-beginnings'

    try:
        if selected == 'mnh-beginnings':
            return html.Div(), {}, {'display': 'none'}
        result = _render_mnh_dashboard_view(selected, state, views)
        _MNID_EXECUTIVE_DISK_CACHE.set(f'ec:{executive_token}', views, expire=_MNID_UI_CACHE_TTL_SECONDS)
        return result, {'display': 'none'}, {}
    except Exception as exc:
        _LOGGER.exception('Failed to render MNH dashboard tab %s: %s', selected, exc)
        return (
            html.Div(
                f'Tab failed to load ({selected}): {exc}',
                style={'padding': '24px', 'color': '#dc2626', 'fontSize': '13px'},
            ),
            {'display': 'none'},
            {},
        )





@callback(
    Output({'type': 'mnid-cp-graph',   'chart': MATCH}, 'figure'),
    Output({'type': 'mnid-cp-caption', 'chart': MATCH}, 'children'),
    Input({'type': 'mnid-cp-grain',    'chart': MATCH}, 'value'),
    State({'type': 'mnid-cp-series',   'chart': MATCH}, 'data'),
    State({'type': 'mnid-cp-meta',     'chart': MATCH}, 'data'),
    prevent_initial_call=False,
)
def _update_country_profile_chart_grain(grain, stored_rows, meta):
    if not stored_rows:
        raise PreventUpdate
    series_df = pd.DataFrame(stored_rows)
    if series_df.empty:
        raise PreventUpdate
    meta = meta or {}
    if 'month' in series_df.columns:
        series_df['month'] = pd.to_datetime(series_df['month'], errors='coerce')
    grain    = (grain or 'monthly').strip().lower()
    title    = meta.get('title') or 'Chart'
    accent   = meta.get('accent') or '#15803D'
    y_title  = meta.get('y_title') or 'Cases'
    is_multi = bool(meta.get('multi'))
    if is_multi:
        bucketed = bucket_multi_series(series_df.copy(), grain)
        figure   = _multi_run_chart(bucketed, title, y_title, grain=grain)
    else:
        bucketed = bucket_time_series(series_df[['month', 'value']].copy(), grain)
        figure   = _run_chart(bucketed, title, accent, y_title, grain=grain)
    caption = describe_grain_window(bucketed, grain)
    return figure, caption


@callback(
    Output('mnid-preload-status', 'data'),
    Input('mnid-background-preload', 'n_intervals'),
    State('mnid-executive-view-store', 'data'),
    State('mnid-active-tab-store', 'data'),
    prevent_initial_call=False,
)
def _preload_mnid_executive_tabs(_tick, executive_token, active_tab):
    if not executive_token:
        raise PreventUpdate

    views = _MNID_EXECUTIVE_DISK_CACHE.get(f'ec:{executive_token}')
    state = _MNID_EXECUTIVE_DISK_CACHE.get(f'ed:{executive_token}')
    if views is None or state is None:
        raise PreventUpdate

    _ndf_available = _get_network_df_from_state(state) is not None
    _LOGGER.info('MNID background preload firing: ndf_available=%s', _ndf_available)

    def _do_preload():
        for tab_value in ['maternal-dashboard', 'newborn-dashboard']:
            if tab_value == active_tab or tab_value in views:
                continue
            if tab_value == 'newborn-dashboard' and state.get('newborn_config') is None:
                continue
            try:
                _LOGGER.info('MNID background preload: building %s', tab_value)
                _build_executive_tab_view(tab_value, views, state)
                _LOGGER.info('MNID background preload: %s done', tab_value)
            except Exception as exc:
                _LOGGER.warning('Background preload failed for executive tab %s: %s', tab_value, exc)

        base_scope_meta  = state.get('scope_meta') or {}
        maternal_config  = state.get('config') or {}
        if maternal_config.get('report_name') == 'Maternal Health':
            maternal_categories = [
                c for c in (maternal_config.get('mnid_categories') or ['ANC', 'Labour', 'PNC'])
                if c in {'ANC', 'Labour', 'PNC'}
            ]
            current_categories = tuple(sorted(base_scope_meta.get('mnid_categories') or []))
            for category in maternal_categories:
                if current_categories == (category,):
                    continue
                try:
                    warm_scope_meta = dict(base_scope_meta)
                    warm_scope_meta['mnid_categories'] = [category]
                    _build_executive_tab_view(
                        'maternal-dashboard', views, state,
                        scope_meta_override=warm_scope_meta,
                        store_in_views=False,
                    )
                except Exception as exc:
                    _LOGGER.warning('Background preload failed for maternal category %s: %s', category, exc)

        _MNID_EXECUTIVE_DISK_CACHE.set(f'ec:{executive_token}', views, expire=_MNID_UI_CACHE_TTL_SECONDS)

    threading.Thread(target=_do_preload, daemon=True, name='mnid-preload').start()
    raise PreventUpdate
