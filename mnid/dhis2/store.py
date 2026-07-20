"""Cached read-only adapter for validated local DHIS2 dashboard output."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .settings import DHIS2Settings
from .status import load_status

_CACHE: dict[str, tuple[int, pd.DataFrame]] = {}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_validated_data(settings: DHIS2Settings | None = None) -> pd.DataFrame:
    """Load current last-known-good output once per file version; never access the network."""
    settings = settings or DHIS2Settings.from_env()
    path = settings.aggregate_data_dir / "current.parquet"
    if not path.exists():
        return pd.DataFrame()
    key = str(path.resolve()); version = path.stat().st_mtime_ns
    cached = _CACHE.get(key)
    if cached and cached[0] == version:
        return cached[1].copy()
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()
    _CACHE[key] = (version, frame)
    return frame.copy()


def invalidate_cache() -> None:
    _CACHE.clear()


def source_metadata(settings: DHIS2Settings | None = None) -> dict[str, Any]:
    """Combine last-known-good metadata and latest attempt status with freshness."""
    settings = settings or DHIS2Settings.from_env()
    metadata = _read_json(settings.aggregate_data_dir / "current_metadata.json")
    attempt = load_status(settings.status_dir)
    last_success = metadata.get("last_synced_at") or attempt.get("last_successful_sync")
    stale = False
    if last_success:
        try:
            synced = datetime.fromisoformat(str(last_success).replace("Z", "+00:00"))
            if synced.tzinfo is None:
                synced = synced.replace(tzinfo=timezone.utc)
            stale = (datetime.now(timezone.utc) - synced).total_seconds() > settings.stale_after_hours * 3600
        except ValueError:
            stale = True
    return {
        "source": "Malawi HMIS DHIS2", "last_successful_sync": last_success,
        "latest_sync_status": attempt.get("status", "never_run"),
        "mapping_version": metadata.get("mapping_version") or attempt.get("mapping_version"),
        "start_period": metadata.get("start_period"), "end_period": metadata.get("end_period"),
        "stale": stale, "available": (settings.aggregate_data_dir / "current.parquet").exists(),
    }


def query_dashboard_data(
    start_date,
    end_date,
    *,
    facility_codes: list[str] | None = None,
    districts: list[str] | None = None,
    settings: DHIS2Settings | None = None,
) -> pd.DataFrame:
    """Apply existing MNID date/facility/district semantics to validated output."""
    frame = load_validated_data(settings)
    if frame.empty:
        return frame
    result = frame.copy()
    start = pd.to_datetime(start_date, errors="coerce")
    end = pd.to_datetime(end_date, errors="coerce")
    period_dates = pd.to_datetime(result["period_start"], errors="coerce")
    if not pd.isna(start): result = result[period_dates >= start]
    if not pd.isna(end): result = result[period_dates <= end]
    if facility_codes:
        result = result[result["facility_code"].astype(str).isin({str(item) for item in facility_codes})]
    elif districts:
        result = result[result["district"].astype(str).isin({str(item) for item in districts})]
    return result.reset_index(drop=True)
