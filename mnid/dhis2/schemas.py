"""Dependency-free structural and semantic validation for DHIS2 configuration."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .exceptions import DHIS2MappingError
from .periods import monthly_periods

UID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{10}$")
ID_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
OPERATIONS = {"direct", "sum", "subtract", "percentage", "sum_indicators"}
VALUE_TYPES = {"count", "percentage", "rate", "ratio", "measurement", "unknown"}
VALIDATION_STATUSES = {"valid", "review_required", "rejected"}
ORG_LEVELS = {"national", "zone", "district", "facility", "community"}


def _fail(messages: list[str]) -> None:
    if messages:
        raise DHIS2MappingError("; ".join(messages))


def _iter_operands(value: Any):
    if isinstance(value, dict):
        if "dx" in value:
            yield value
        for child in value.values():
            yield from _iter_operands(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_operands(child)


def _indicator_references(calculation: Any) -> list[str]:
    refs: list[str] = []
    if not calculation:
        return refs
    if isinstance(calculation, list):
        for value in calculation:
            refs.extend(_indicator_references(value))
        return refs
    if not isinstance(calculation, dict):
        return refs
    for key, value in calculation.items():
        if key == "indicator_ids" and isinstance(value, list):
            refs.extend(str(item) for item in value)
        elif isinstance(value, (dict, list)):
            refs.extend(_indicator_references(value))
    return refs


def validate_indicator_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Validate indicator structure, operands, periods, and dependency graph."""
    errors: list[str] = []
    if data.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    if not str(data.get("mapping_version") or "").strip():
        errors.append("mapping_version is required")
    period = data.get("reporting_period") or {}
    try:
        monthly_periods(period.get("start_period"), period.get("end_period"))
    except Exception as exc:
        errors.append(str(exc))
    indicators = data.get("indicators")
    if not isinstance(indicators, list):
        errors.append("indicators must be an array")
        _fail(errors)
    ids: set[str] = set()
    enabled: dict[str, bool] = {}
    graph: dict[str, list[str]] = {}
    for pos, indicator in enumerate(indicators):
        prefix = f"indicator[{pos}]"
        iid = str(indicator.get("id") or "")
        if not ID_RE.fullmatch(iid):
            errors.append(f"{prefix} has invalid id {iid!r}")
        if iid in ids:
            errors.append(f"duplicate indicator id {iid!r}")
        ids.add(iid)
        enabled[iid] = bool(indicator.get("enabled"))
        if indicator.get("value_type") not in VALUE_TYPES:
            errors.append(f"{iid}: unsupported value_type")
        status = (indicator.get("validation") or {}).get("status")
        if status not in VALIDATION_STATUSES:
            errors.append(f"{iid}: invalid validation status")
        calculation = indicator.get("calculation")
        if enabled[iid] and not calculation:
            errors.append(f"{iid}: enabled indicator has no calculation")
        if calculation:
            operation = calculation.get("operation")
            if operation not in OPERATIONS:
                errors.append(f"{iid}: unsupported operation {operation!r}")
            operands = list(_iter_operands(calculation))
            dx_seen: set[str] = set()
            for item in operands:
                dx = str(item.get("dx") or "")
                parts = dx.split(".")
                if len(parts) not in {1, 2} or any(not UID_RE.fullmatch(part) for part in parts):
                    errors.append(f"{iid}: invalid operand {dx!r}")
                if dx in dx_seen:
                    errors.append(f"{iid}: duplicate operand {dx!r}")
                dx_seen.add(dx)
            if operation in {"direct", "sum"} and not operands:
                errors.append(f"{iid}: {operation} requires operands")
            if operation == "percentage":
                if not list(_iter_operands(calculation.get("numerator"))):
                    errors.append(f"{iid}: percentage requires numerator operands")
                if not list(_iter_operands(calculation.get("denominator"))):
                    errors.append(f"{iid}: percentage requires denominator operands")
        graph[iid] = _indicator_references(calculation)
    for iid, refs in graph.items():
        for ref in refs:
            if ref not in ids:
                errors.append(f"{iid}: unknown indicator reference {ref!r}")
            elif enabled.get(iid) and not enabled.get(ref):
                errors.append(f"{iid}: active indicator depends on disabled {ref!r}")

    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(iid: str):
        if iid in visiting:
            errors.append(f"circular indicator dependency involving {iid!r}")
            return
        if iid in visited:
            return
        visiting.add(iid)
        for ref in graph.get(iid, []):
            if ref in graph:
                visit(ref)
        visiting.remove(iid)
        visited.add(iid)
    for iid in graph:
        visit(iid)
    _fail(errors)
    return data


def _month(value: Any, field: str, errors: list[str]) -> tuple[int, int] | None:
    if value is None:
        return None
    text = str(value)
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", text):
        errors.append(f"{field} must be YYYY-MM")
        return None
    return int(text[:4]), int(text[5:])


def validate_organisation_units(data: dict[str, Any], *, require_enabled: bool = False) -> dict[str, Any]:
    """Validate organisation-unit IDs, levels, active dates, and local mappings."""
    errors: list[str] = []
    if data.get("schema_version") != "1.0":
        errors.append("organisation-unit schema_version must be '1.0'")
    units = data.get("organisation_units")
    if not isinstance(units, list):
        errors.append("organisation_units must be an array")
        _fail(errors)
    seen_ids: set[str] = set()
    active_local: set[tuple[str, str]] = set()
    for pos, unit in enumerate(units):
        uid = str(unit.get("org_unit_id") or "")
        if not UID_RE.fullmatch(uid):
            errors.append(f"organisation_units[{pos}] has invalid org_unit_id")
        if uid in seen_ids:
            errors.append(f"duplicate organisation-unit id {uid!r}")
        seen_ids.add(uid)
        level = unit.get("level")
        if level not in ORG_LEVELS:
            errors.append(f"{uid}: unsupported level {level!r}")
        if not str(unit.get("name") or "").strip():
            errors.append(f"{uid}: name is required")
        start = _month(unit.get("active_from"), f"{uid}.active_from", errors)
        end = _month(unit.get("active_to"), f"{uid}.active_to", errors)
        if start and end and end < start:
            errors.append(f"{uid}: active_to is before active_from")
        local_code = unit.get("local_facility_code")
        if unit.get("enabled") and local_code:
            key = (str(local_code), str(level))
            if key in active_local:
                errors.append(f"duplicate active local mapping {key[0]!r} at level {key[1]!r}")
            active_local.add(key)
    if require_enabled and not any(unit.get("enabled") for unit in units):
        errors.append("No enabled organisation units are configured; add an approved crosswalk before live sync")
    _fail(errors)
    return data
