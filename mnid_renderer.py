"""Compatibility entry point for the MNID dashboard."""

from mnid.app import render_mnid_dashboard, update_heatmap_view, update_compare_charts

__all__ = [
    'render_mnid_dashboard',
    'update_heatmap_view',
    'update_compare_charts',
]
