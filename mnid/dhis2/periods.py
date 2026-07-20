"""Deterministic DHIS2 monthly-period utilities."""

from __future__ import annotations

import calendar
import re
from datetime import date

from .exceptions import DHIS2ConfigurationError

PERIOD_RE = re.compile(r"^(\d{4})(0[1-9]|1[0-2])$")
DEFAULT_START_PERIOD = "202504"
DEFAULT_END_PERIOD = "202605"


def validate_monthly_period(period: str) -> str:
    """Return a valid `YYYYMM` period or raise a configuration error."""
    value = str(period or "").strip()
    if not PERIOD_RE.fullmatch(value):
        raise DHIS2ConfigurationError(
            f"Invalid monthly period {value!r}; expected YYYYMM with month 01-12"
        )
    return value


def monthly_periods(start_period: str, end_period: str) -> list[str]:
    """Generate an inclusive, ordered monthly range."""
    start = validate_monthly_period(start_period)
    end = validate_monthly_period(end_period)
    if start > end:
        raise DHIS2ConfigurationError(
            f"Start period {start} must not be after end period {end}"
        )
    year, month = int(start[:4]), int(start[4:])
    end_year, end_month = int(end[:4]), int(end[4:])
    result: list[str] = []
    while (year, month) <= (end_year, end_month):
        result.append(f"{year:04d}{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return result


def period_start_date(period: str) -> date:
    """Return the first calendar day represented by a monthly period."""
    value = validate_monthly_period(period)
    return date(int(value[:4]), int(value[4:]), 1)


def period_end_date(period: str) -> date:
    """Return the final calendar day represented by a monthly period."""
    value = validate_monthly_period(period)
    year, month = int(value[:4]), int(value[4:])
    return date(year, month, calendar.monthrange(year, month)[1])
