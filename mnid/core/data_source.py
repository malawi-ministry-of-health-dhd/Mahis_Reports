"""Configuration-driven data access policy for MNID dashboards.

Visual components should ask this module which route and reporting window to
use instead of branching independently on ``MNID_DATA_SOURCE``.  MAHIS keeps
its encounter-level parquet workflow; DHIS2 uses the published MNID aggregate.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging

import pandas as pd

_LOGGER = logging.getLogger(__name__)
_SUPPORTED_SOURCES = {'mahis', 'dhis2'}


def _configured_source() -> str:
    try:
        from config import MNID_DATA_SOURCE
        source = str(MNID_DATA_SOURCE or 'mahis').strip().lower()
    except Exception:
        source = 'mahis'
    if source not in _SUPPORTED_SOURCES:
        _LOGGER.warning('Unsupported MNID_DATA_SOURCE=%r; falling back to mahis', source)
        return 'mahis'
    return source


@dataclass(frozen=True)
class MNIDDataSource:
    """Resolved MNID data-source behavior for one request."""

    source: str
    data_route: str = 'default'

    @property
    def route(self) -> str:
        return 'dhis2' if self.source == 'dhis2' else self.data_route

    @property
    def requires_raw_dataset(self) -> bool:
        return self.source == 'mahis'

    def aggregate(self) -> pd.DataFrame | None:
        from mnid.aggregation.store import get_aggregate
        return get_aggregate(route=self.route)

    def reporting_bounds(self) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
        """Return the source's available aggregate period, when authoritative."""
        aggregate = self.aggregate()
        if aggregate is None or aggregate.empty or 'period_start' not in aggregate.columns:
            return None, None
        periods = pd.to_datetime(aggregate['period_start'], errors='coerce').dropna()
        if periods.empty:
            return None, None
        start = periods.min().normalize()
        end = periods.max().normalize()
        if self.source == 'dhis2':
            end = (end + pd.offsets.MonthEnd(0)).normalize()
        return start, end

    def default_window(self, days: int = 30) -> tuple[object, object] | None:
        """Return a recent window anchored to this source's latest report."""
        _, available_end = self.reporting_bounds()
        if available_end is None:
            return None
        start = available_end - pd.Timedelta(days=max(days - 1, 0))
        return start.date(), available_end.date()

    def resolve_window(self, start_date, end_date) -> tuple[object, object]:
        """Preserve overlapping ranges and recover ranges outside source data."""
        if self.source != 'dhis2':
            return start_date, end_date
        available_start, available_end = self.reporting_bounds()
        fallback = self.default_window()
        if available_start is None or available_end is None or fallback is None:
            return start_date, end_date
        requested_start = pd.to_datetime(start_date, errors='coerce')
        requested_end = pd.to_datetime(end_date, errors='coerce')
        if pd.isna(requested_start) or pd.isna(requested_end):
            return fallback
        if requested_end < available_start or requested_start > available_end:
            return fallback
        return start_date, end_date

    def comparison_dimensions(self) -> tuple[list[str], list[str]] | None:
        """Return aggregate-backed facility/district values for DHIS2 controls."""
        if self.source != 'dhis2':
            return None
        aggregate = self.aggregate()
        if aggregate is None or aggregate.empty:
            return None
        facilities = sorted({
            str(value).strip()
            for value in aggregate.get('facility_code', pd.Series(dtype=object)).dropna()
            if str(value).strip()
        })
        districts = sorted({
            str(value).strip()
            for value in aggregate.get('district', pd.Series(dtype=object)).dropna()
            if str(value).strip()
        })
        return facilities, districts


def get_mnid_data_source(data_route: str = 'default', source: str | None = None) -> MNIDDataSource:
    resolved = str(source or _configured_source()).strip().lower()
    if resolved not in _SUPPORTED_SOURCES:
        resolved = 'mahis'
    return MNIDDataSource(source=resolved, data_route=data_route or 'default')
