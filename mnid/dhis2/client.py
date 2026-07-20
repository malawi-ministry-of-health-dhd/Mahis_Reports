"""Secure, bounded DHIS2 Analytics API client and header-driven parser."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

import requests

from .exceptions import (
    DHIS2AuthenticationError,
    DHIS2AuthorizationError,
    DHIS2ConnectionError,
    DHIS2RateLimitError,
    DHIS2RequestError,
    DHIS2ResponseError,
    DHIS2TimeoutError,
)
from .settings import DHIS2Settings

_LOG = logging.getLogger(__name__)
_REQUIRED_HEADERS = {"dx", "pe", "ou", "value"}


@dataclass(frozen=True)
class AnalyticsValue:
    """One validated atomic DHIS2 Analytics value."""

    dx: str
    period: str
    org_unit_id: str
    value: Decimal
    raw_value: str


class DHIS2Client:
    """A dependency-injectable client with bounded transient retries."""

    def __init__(
        self,
        settings: DHIS2Settings,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not settings.username or not settings.password:
            raise DHIS2AuthenticationError("Live DHIS2 client requires configured credentials")
        self.settings = settings
        self.session = session or requests.Session()
        self._owns_session = session is None
        self.sleep = sleep
        self.session.auth = (settings.username, settings.password)
        self.session.headers.update({"Accept": "application/json", "User-Agent": "MaHIS-MNID-DHIS2/1.0"})

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def analytics(self, dx: list[str], periods: list[str], org_units: list[str], *, sync_run_id: str, request_id: str) -> dict[str, Any]:
        """Request one pre-batched Analytics payload."""
        if not dx or not periods or not org_units:
            raise DHIS2RequestError("Analytics dimensions dx, pe, and ou must be non-empty")
        params = [
            ("dimension", f"dx:{';'.join(dx)}"),
            ("dimension", f"pe:{';'.join(periods)}"),
            ("dimension", f"ou:{';'.join(org_units)}"),
            ("skipMeta", "false"),
        ]
        for attempt in range(self.settings.max_retries + 1):
            _LOG.info(
                "DHIS2 analytics request sync_run_id=%s request_id=%s attempt=%d dx=%d periods=%d org_units=%d",
                sync_run_id, request_id, attempt + 1, len(dx), len(periods), len(org_units),
            )
            try:
                response = self.session.get(
                    self.settings.analytics_url,
                    params=params,
                    timeout=(self.settings.connect_timeout_seconds, self.settings.read_timeout_seconds),
                    verify=self.settings.verify_tls,
                )
            except requests.Timeout as exc:
                if attempt < self.settings.max_retries:
                    self._backoff(attempt)
                    continue
                raise DHIS2TimeoutError("DHIS2 request timed out after bounded retries") from exc
            except requests.ConnectionError as exc:
                if attempt < self.settings.max_retries:
                    self._backoff(attempt)
                    continue
                raise DHIS2ConnectionError("Unable to connect to DHIS2 after bounded retries") from exc

            if response.status_code == 401:
                raise DHIS2AuthenticationError("DHIS2 authentication failed")
            if response.status_code == 403:
                raise DHIS2AuthorizationError("DHIS2 authorization failed")
            if response.status_code == 400:
                raise DHIS2RequestError("DHIS2 rejected the Analytics query (HTTP 400)")
            if response.status_code == 404:
                raise DHIS2RequestError("DHIS2 Analytics endpoint was not found (HTTP 404)")
            if response.status_code == 409:
                raise DHIS2RequestError("DHIS2 could not execute the Analytics query (HTTP 409)")
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt < self.settings.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    self._backoff(attempt, retry_after)
                    continue
                if response.status_code == 429:
                    raise DHIS2RateLimitError("DHIS2 rate limit persisted after bounded retries")
                raise DHIS2RequestError(f"DHIS2 transient server failure persisted (HTTP {response.status_code})")
            if not 200 <= response.status_code < 300:
                raise DHIS2RequestError(f"Unexpected DHIS2 HTTP status {response.status_code}")
            content_type = response.headers.get("Content-Type", "").lower()
            if "json" not in content_type:
                raise DHIS2ResponseError("DHIS2 response Content-Type is not JSON")
            try:
                payload = response.json()
            except (ValueError, requests.JSONDecodeError) as exc:
                raise DHIS2ResponseError("DHIS2 response contains malformed JSON") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("headers"), list) or not isinstance(payload.get("rows"), list):
                raise DHIS2ResponseError("DHIS2 Analytics response must contain headers and rows arrays")
            return payload
        raise DHIS2RequestError("Unreachable retry state")

    def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        delay = min(30.0, float(2**attempt))
        if retry_after:
            try:
                delay = min(60.0, max(delay, float(retry_after)))
            except ValueError:
                pass
        self.sleep(delay)


def parse_analytics_response(payload: dict[str, Any]) -> tuple[list[AnalyticsValue], list[dict[str, Any]]]:
    """Parse dynamic Analytics headers; reject malformed rows without inventing zeroes."""
    headers = payload.get("headers")
    rows = payload.get("rows")
    if not isinstance(headers, list) or not isinstance(rows, list):
        raise DHIS2ResponseError("Analytics response must contain headers and rows arrays")
    names = [str(item.get("name") if isinstance(item, dict) else item) for item in headers]
    positions = {name: index for index, name in enumerate(names)}
    missing = _REQUIRED_HEADERS - positions.keys()
    if missing:
        raise DHIS2ResponseError(f"Analytics response is missing required headers: {', '.join(sorted(missing))}")
    accepted: list[AnalyticsValue] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row_number, row in enumerate(rows, 1):
        if not isinstance(row, list) or len(row) < len(headers):
            rejected.append({"row_number": row_number, "reason": "malformed_row", "row": row})
            continue
        dx, pe, ou = (str(row[positions[key]]) for key in ("dx", "pe", "ou"))
        raw = str(row[positions["value"]])
        key = (dx, pe, ou)
        if key in seen:
            rejected.append({"row_number": row_number, "reason": "duplicate_dimension_key", "row": row})
            continue
        try:
            value = Decimal(raw)
            if not value.is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            rejected.append({"row_number": row_number, "reason": "invalid_numeric_value", "row": row})
            continue
        seen.add(key)
        accepted.append(AnalyticsValue(dx=dx, period=pe, org_unit_id=ou, value=value, raw_value=raw))
    accepted.sort(key=lambda item: (item.period, item.org_unit_id, item.dx))
    return accepted, rejected
