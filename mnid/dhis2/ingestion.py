"""Query planning and end-to-end ingestion orchestration."""

from __future__ import annotations

import itertools
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable

from .calculations import calculate_indicators
from .client import AnalyticsValue, DHIS2Client, parse_analytics_response
from .exceptions import DHIS2SyncError
from .mappings import atomic_dx_values
from .periods import monthly_periods, period_end_date, period_start_date
from .settings import DHIS2Settings
from .storage import atomic_json, atomic_parquet, exclusive_sync_lock, store_raw_audit
from .validation import validate_sync_data


@dataclass(frozen=True)
class QueryRequest:
    request_id: str
    dx: tuple[str, ...]
    periods: tuple[str, ...]
    org_units: tuple[str, ...]


def _batches(values: Iterable[str], size: int) -> list[tuple[str, ...]]:
    items = list(values)
    return [tuple(items[pos:pos + size]) for pos in range(0, len(items), size)]


def build_query_plan(mapping: dict[str, Any], units: list[dict[str, Any]], periods: list[str], settings: DHIS2Settings) -> list[QueryRequest]:
    """Build stable Cartesian request batches for dx, period, and ou dimensions."""
    dx_batches = _batches(atomic_dx_values(mapping), settings.dx_batch_size)
    pe_batches = _batches(periods, settings.period_batch_size)
    ou_batches = _batches(sorted(unit["org_unit_id"] for unit in units if unit.get("enabled")), settings.org_unit_batch_size)
    plan: list[QueryRequest] = []
    for number, (dx, pe, ou) in enumerate(itertools.product(dx_batches, pe_batches, ou_batches), 1):
        plan.append(QueryRequest(f"request-{number:04d}", dx, pe, ou))
    return plan


def query_plan_summary(mapping, units, periods, plan, settings) -> dict[str, Any]:
    return {
        "endpoint": settings.analytics_url,
        "enabled_indicators": sum(bool(item.get("enabled")) for item in mapping["indicators"]),
        "unique_dx_operands": len(atomic_dx_values(mapping)),
        "period_count": len(periods),
        "organisation_unit_count": sum(bool(item.get("enabled")) for item in units),
        "planned_request_count": len(plan),
        "periods": periods,
    }


def _normalized_record(row: AnalyticsValue, unit: dict[str, Any], sync_run_id: str, mapping_version: str, retrieved_at: str) -> dict[str, Any]:
    parts = row.dx.split(".", 1)
    return {
        "source": "Malawi HMIS DHIS2", "dx": row.dx,
        "data_element_id": parts[0], "category_option_combo_id": parts[1] if len(parts) == 2 else None,
        "period": row.period, "period_start": period_start_date(row.period).isoformat(),
        "period_end": period_end_date(row.period).isoformat(), "org_unit_id": row.org_unit_id,
        "org_unit_name": unit.get("name"), "district_name": unit.get("district"),
        "facility_code": unit.get("local_facility_code"), "value": row.value,
        "raw_value": row.raw_value, "retrieved_at": retrieved_at, "sync_run_id": sync_run_id,
        "mapping_version": mapping_version, "validation_status": "valid",
    }


def run_ingestion(
    settings: DHIS2Settings,
    mapping: dict[str, Any],
    units: list[dict[str, Any]],
    periods: list[str],
    *,
    client_factory: Callable[[DHIS2Settings], DHIS2Client] = DHIS2Client,
) -> dict[str, Any]:
    """Pull, validate, and atomically publish; never replace good data on failure."""
    enabled_units = [item for item in units if item.get("enabled")]
    plan = build_query_plan(mapping, enabled_units, periods, settings)
    if not plan:
        raise DHIS2SyncError("Query plan is empty")
    sync_run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()
    atomic_rows: list[AnalyticsValue] = []
    rejected_rows: list[dict[str, Any]] = []
    with exclusive_sync_lock(settings.status_dir):
        completed = 0
        with client_factory(settings) as client:
            for request in plan:
                requested_at = datetime.now(timezone.utc).isoformat()
                payload = client.analytics(list(request.dx), list(request.periods), list(request.org_units), sync_run_id=sync_run_id, request_id=request.request_id)
                parsed, rejected = parse_analytics_response(payload)
                completed += 1; atomic_rows.extend(parsed); rejected_rows.extend(rejected)
                store_raw_audit(settings.raw_data_dir, sync_run_id, request.request_id, {
                    "sync_run_id": sync_run_id, "request_id": request.request_id,
                    "endpoint": settings.analytics_url, "dx": list(request.dx),
                    "periods": list(request.periods), "organisation_units": list(request.org_units),
                    "requested_at": requested_at, "completed_at": datetime.now(timezone.utc).isoformat(),
                    "http_status": 200, "response_row_count": len(payload.get("rows", [])),
                }, payload)
        unique: dict[tuple[str, str, str], AnalyticsValue] = {}
        for row in atomic_rows:
            key = (row.dx, row.period, row.org_unit_id)
            if key in unique:
                rejected_rows.append({"reason": "duplicate_across_requests", "key": key})
            else:
                unique[key] = row
        atomic_rows = sorted(unique.values(), key=lambda row: (row.period, row.org_unit_id, row.dx))
        atomic_index = {(row.dx, row.period, row.org_unit_id): row.value for row in atomic_rows}
        calculated = calculate_indicators(mapping, atomic_index, periods, enabled_units)
        retrieved_at = datetime.now(timezone.utc).isoformat()
        normalized = [_normalized_record(row, next(unit for unit in enabled_units if unit["org_unit_id"] == row.org_unit_id), sync_run_id, mapping["mapping_version"], retrieved_at) for row in atomic_rows]
        for row in calculated:
            row.update({
                "period_start": period_start_date(row["period"]).isoformat(),
                "period_end": period_end_date(row["period"]).isoformat(),
                "last_synced_at": retrieved_at, "mapping_version": mapping["mapping_version"],
                "sync_run_id": sync_run_id,
            })
        validation = validate_sync_data(mapping, atomic_rows, calculated, periods, enabled_units, rejected_rows=rejected_rows, completed_requests=completed, planned_requests=len(plan))
        atomic_json(settings.normalized_data_dir / sync_run_id / "validation.json", validation)
        atomic_parquet(settings.normalized_data_dir / sync_run_id / "atomic_values.parquet", normalized)
        atomic_parquet(settings.aggregate_data_dir / f".{sync_run_id}.candidate.parquet", calculated)
        if not validation["publishable"]:
            (settings.aggregate_data_dir / f".{sync_run_id}.candidate.parquet").unlink(missing_ok=True)
            raise DHIS2SyncError("Synchronization validation failed; previous validated dataset retained")
        atomic_parquet(settings.aggregate_data_dir / "current.parquet", calculated)
        atomic_json(settings.aggregate_data_dir / "current_metadata.json", {
            "source": "Malawi HMIS DHIS2", "sync_run_id": sync_run_id,
            "mapping_version": mapping["mapping_version"], "last_synced_at": retrieved_at,
            "start_period": periods[0], "end_period": periods[-1], "validation_status": validation["status"],
        })
        (settings.aggregate_data_dir / f".{sync_run_id}.candidate.parquet").unlink(missing_ok=True)
        return {
            "source": "Malawi HMIS DHIS2", "status": "success", "sync_run_id": sync_run_id,
            "started_at": started_at, "completed_at": retrieved_at,
            "start_period": periods[0], "end_period": periods[-1], "period_count": len(periods),
            "organisation_unit_count": len(enabled_units), "requested_dx_count": len(atomic_dx_values(mapping)),
            "request_count": len(plan), "successful_request_count": completed, "failed_request_count": 0,
            "received_row_count": len(atomic_rows) + len(rejected_rows), "normalized_row_count": len(normalized),
            "calculated_record_count": len(calculated), "warning_count": validation["warning_count"],
            "rejected_count": validation["rejected_row_count"], "last_successful_sync": retrieved_at,
            "mapping_version": mapping["mapping_version"], "published": True, "error": None,
        }
