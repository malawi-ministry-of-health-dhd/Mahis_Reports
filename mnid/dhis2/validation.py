"""Completeness and semantic validation for normalized and calculated DHIS2 data."""

from __future__ import annotations

from typing import Any

from .client import AnalyticsValue
from .mappings import atomic_dx_values


def validate_sync_data(
    mapping: dict[str, Any],
    atomic_rows: list[AnalyticsValue],
    calculated_rows: list[dict[str, Any]],
    periods: list[str],
    organisation_units: list[dict[str, Any]],
    *,
    rejected_rows: list[dict[str, Any]] | None = None,
    completed_requests: int,
    planned_requests: int,
) -> dict[str, Any]:
    """Return a machine-readable validation report; rejected/partial is not publishable."""
    rejected_rows = rejected_rows or []
    expected_dx = set(atomic_dx_values(mapping))
    expected_periods = set(periods)
    expected_ou = {item["org_unit_id"] for item in organisation_units}
    unknown_dx = sorted({row.dx for row in atomic_rows} - expected_dx)
    invalid_periods = sorted({row.period for row in atomic_rows} - expected_periods)
    invalid_org_units = sorted({row.org_unit_id for row in atomic_rows} - expected_ou)
    missing_inputs = sum(row.get("validation_status") == "partial" for row in calculated_rows)
    warnings = sum(row.get("validation_status") == "warning" for row in calculated_rows)
    errors: list[str] = []
    if completed_requests != planned_requests:
        errors.append("Not every planned request completed successfully.")
    if rejected_rows:
        errors.append("One or more Analytics rows were rejected.")
    if unknown_dx:
        errors.append("Response contained unknown dx values.")
    if invalid_periods:
        errors.append("Response contained periods outside the query plan.")
    if invalid_org_units:
        errors.append("Response contained unknown organisation units.")
    if missing_inputs:
        errors.append("Calculated output is incomplete because required operands are missing.")
    status = "rejected" if errors else ("warning" if warnings else "valid")
    return {
        "status": status,
        "publishable": status in {"valid", "warning"},
        "mapping_version": mapping["mapping_version"],
        "planned_requests": planned_requests, "completed_requests": completed_requests,
        "atomic_row_count": len(atomic_rows), "calculated_record_count": len(calculated_rows),
        "rejected_row_count": len(rejected_rows), "missing_input_count": missing_inputs,
        "warning_count": warnings, "unknown_dx": unknown_dx,
        "invalid_periods": invalid_periods, "invalid_org_units": invalid_org_units,
        "errors": errors,
    }
