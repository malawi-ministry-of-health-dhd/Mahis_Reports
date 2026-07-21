"""Environment-backed settings for explicit MNID DHIS2 synchronization."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from .exceptions import DHIS2ConfigurationError
from .periods import DEFAULT_END_PERIOD, DEFAULT_START_PERIOD, monthly_periods

_MNID_ROOT = Path(__file__).resolve().parents[1]
_DATA_ROOT = _MNID_ROOT / "data" / "dhis2"


def _boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise DHIS2ConfigurationError(f"{name} must be true or false")


def _positive_int(value: str, name: str, *, allow_zero: bool = False) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DHIS2ConfigurationError(f"{name} must be an integer") from exc
    minimum = 0 if allow_zero else 1
    if parsed < minimum:
        raise DHIS2ConfigurationError(f"{name} must be at least {minimum}")
    return parsed


def _url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise DHIS2ConfigurationError(
            "MNH_DHIS2_BASE_URL must be an HTTPS URL without embedded credentials"
        )
    return candidate


@dataclass(frozen=True)
class DHIS2Settings:
    """Validated immutable settings. Credentials are required only for live sync."""

    base_url: str
    username: str | None
    password: str | None
    start_period: str
    end_period: str
    connect_timeout_seconds: int
    read_timeout_seconds: int
    max_retries: int
    verify_tls: bool
    dx_batch_size: int
    org_unit_batch_size: int
    period_batch_size: int
    raw_data_dir: Path
    normalized_data_dir: Path
    aggregate_data_dir: Path
    status_dir: Path
    stale_after_hours: int

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        require_credentials: bool = False,
    ) -> "DHIS2Settings":
        """Load settings without mutating global environment state."""
        env = os.environ if environ is None else environ
        base_url = _url(env.get("MNH_DHIS2_BASE_URL", "https://dhis2.health.gov.mw"))
        start = env.get("MNH_DHIS2_START_PERIOD", DEFAULT_START_PERIOD)
        end = env.get("MNH_DHIS2_END_PERIOD", DEFAULT_END_PERIOD)
        monthly_periods(start, end)
        username = env.get("MNH_DHIS2_USERNAME") or None
        password = env.get("MNH_DHIS2_PASSWORD") or None
        if require_credentials and (not username or not password):
            raise DHIS2ConfigurationError(
                "MNH_DHIS2_USERNAME and MNH_DHIS2_PASSWORD are required for live synchronization"
            )
        return cls(
            base_url=base_url,
            username=username,
            password=password,
            start_period=start,
            end_period=end,
            connect_timeout_seconds=_positive_int(env.get("MNH_DHIS2_CONNECT_TIMEOUT_SECONDS", "10"), "MNH_DHIS2_CONNECT_TIMEOUT_SECONDS"),
            read_timeout_seconds=_positive_int(env.get("MNH_DHIS2_READ_TIMEOUT_SECONDS", "60"), "MNH_DHIS2_READ_TIMEOUT_SECONDS"),
            max_retries=_positive_int(env.get("MNH_DHIS2_MAX_RETRIES", "3"), "MNH_DHIS2_MAX_RETRIES", allow_zero=True),
            verify_tls=_boolean(env.get("MNH_DHIS2_VERIFY_TLS", "true"), "MNH_DHIS2_VERIFY_TLS"),
            dx_batch_size=_positive_int(env.get("MNH_DHIS2_DX_BATCH_SIZE", "30"), "MNH_DHIS2_DX_BATCH_SIZE"),
            org_unit_batch_size=_positive_int(env.get("MNH_DHIS2_ORG_UNIT_BATCH_SIZE", "10"), "MNH_DHIS2_ORG_UNIT_BATCH_SIZE"),
            period_batch_size=_positive_int(env.get("MNH_DHIS2_PERIOD_BATCH_SIZE", "14"), "MNH_DHIS2_PERIOD_BATCH_SIZE"),
            raw_data_dir=Path(env.get("MNH_DHIS2_RAW_DATA_DIR", str(_DATA_ROOT / "raw"))),
            normalized_data_dir=Path(env.get("MNH_DHIS2_NORMALIZED_DATA_DIR", str(_DATA_ROOT / "normalized"))),
            aggregate_data_dir=Path(env.get("MNH_DHIS2_AGGREGATE_DATA_DIR", str(_DATA_ROOT / "aggregates"))),
            status_dir=Path(env.get("MNH_DHIS2_STATUS_DIR", str(_DATA_ROOT / "status"))),
            stale_after_hours=_positive_int(env.get("MNH_DHIS2_STALE_AFTER_HOURS", "48"), "MNH_DHIS2_STALE_AFTER_HOURS"),
        )

    @property
    def analytics_url(self) -> str:
        return f"{self.base_url}/api/analytics.json"
