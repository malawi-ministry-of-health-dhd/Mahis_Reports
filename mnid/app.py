"""
Entry point for the MNID dashboard.

This file re-exports everything so existing callers (app.py, mnid_renderer.py,
pages/home.py) don't need to know about the internal sub-package layout.

Real code lives in:
  mnid/core/     — constants, cache, data_utils, indicators
  mnid/charts/   — chart_helpers, heatmap, coverage, layout, geo_utils
  mnid/views/    — kpi_engine, trends, service_table, callbacks, renderer, executive_views
  mnid/aggregation/, mnid/components/, mnid/dashboards/
"""

from mnid.core.cache import (  # noqa: F401
    _dk, _trim_cache, _agg_version_stamp,
    _executive_view_cache_key, _country_profile_cache_key,
    _load_dashboard_tab_config, _resolve_scope_filters,
    _get_network_df_from_state, clear_runtime_caches,
    _MNID_EXECUTIVE_DISK_CACHE, _MNID_UI_CACHE_TTL_SECONDS,
    _network_df_cache, _NETWORK_DF_CACHE_MAX,
    _worker_view_cache, _WORKER_VIEW_CACHE_MAX,
    _MNID_WARNED_MESSAGES, _COUNTRY_PROFILE_RENDER_VERSION,
)

from mnid.views.kpi_engine import (  # noqa: F401
    _aggregate_grain_for_window, _build_agg_batch, _batch_cov,
    _programme_activity_counts, _load_mnid_report_config,
    _build_mnid_indicator_content, _get_facility_df_from_state,
    _resolve_heatmap_store,
)

from mnid.views.trends import (  # noqa: F401
    _MNID_SCROLLSPY_CLIENTSIDE, _trend_period_context,
    _trend_scope_filters, _location_options_for_df,
    _indicator_run_fig, _run_chart_cards, _trend_switcher,
    _DEFAULT_TREND_INDICATOR_LIMIT, update_trend_chart,
)

from mnid.views.service_table import (  # noqa: F401
    _encounter_slice, _count_entities, _concept_count,
    _service_table_payload, _service_table_fig, _service_stack_fig,
    _service_stack_overview_fig, _service_snapshot_view,
    _location_trend_fig, _service_table_switcher, update_service_table,
)

from mnid.views.callbacks import (  # noqa: F401
    update_heatmap_view, sync_district_focus_from_treemap,
    update_performance_heatmap, update_compare_charts,
    register_mnid_callbacks, _COMPARE_COLORS,
)

from mnid.views.renderer import (  # noqa: F401
    _mnid_loading_placeholder, prewarm_cache, _prewarm_country_profile,
    render_mnid_dashboard, _build_executive_tab_view,
    _render_mnid_executive_tab, _update_country_profile_chart_grain,
    _preload_mnid_executive_tabs,
)
