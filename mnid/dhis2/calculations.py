"""Deterministic MNH indicator calculations over normalized atomic values."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from .mappings import dependency_order

AtomicKey = tuple[str, str, str]
IndicatorKey = tuple[str, str, str]


def _sum_operands(
    section: Mapping[str, Any] | None,
    atomic: Mapping[AtomicKey, Decimal],
    period: str,
    org_unit_id: str,
) -> Decimal | None:
    operands = list((section or {}).get("operands") or [])
    if not operands:
        return None
    values = [atomic.get((item["dx"], period, org_unit_id)) for item in operands]
    if any(value is None for value in values):
        return None
    return sum(values, Decimal("0"))


def _sum_indicator_refs(
    section: Mapping[str, Any] | None,
    calculated: Mapping[IndicatorKey, dict[str, Any]],
    period: str,
    org_unit_id: str,
) -> Decimal | None:
    refs = list((section or {}).get("indicator_ids") or [])
    if not refs:
        return None
    values = [calculated.get((iid, period, org_unit_id), {}).get("value") for iid in refs]
    if any(value is None for value in values):
        return None
    return sum((Decimal(str(value)) for value in values), Decimal("0"))


def _section_value(section, atomic, calculated, period, org_unit_id) -> Decimal | None:
    if not section:
        return None
    atomic_value = _sum_operands(section, atomic, period, org_unit_id)
    refs_value = _sum_indicator_refs(section, calculated, period, org_unit_id)
    if atomic_value is None:
        return refs_value
    if refs_value is None:
        return atomic_value
    return atomic_value + refs_value


def calculate_indicators(
    mapping: dict[str, Any],
    atomic: Mapping[AtomicKey, Decimal],
    periods: list[str],
    organisation_units: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Calculate all enabled indicators in dependency order for every period/unit."""
    calculated: dict[IndicatorKey, dict[str, Any]] = {}
    output: list[dict[str, Any]] = []
    for indicator in dependency_order(mapping):
        calculation = indicator["calculation"]
        operation = calculation["operation"]
        for period in periods:
            for unit in organisation_units:
                org_unit_id = unit["org_unit_id"]
                numerator = denominator = None
                if operation in {"direct", "sum"}:
                    value = _sum_operands(calculation, atomic, period, org_unit_id)
                elif operation == "sum_indicators":
                    value = _sum_indicator_refs(calculation, calculated, period, org_unit_id)
                elif operation == "subtract":
                    minuend = _section_value(calculation.get("minuend"), atomic, calculated, period, org_unit_id)
                    subtrahend = _section_value(calculation.get("subtrahend"), atomic, calculated, period, org_unit_id)
                    value = None if minuend is None or subtrahend is None else minuend - subtrahend
                elif operation == "percentage":
                    numerator = _section_value(calculation.get("numerator"), atomic, calculated, period, org_unit_id)
                    denominator = _section_value(calculation.get("denominator"), atomic, calculated, period, org_unit_id)
                    value = None if numerator is None or denominator in {None, Decimal("0")} else (
                        numerator / denominator * Decimal(str(calculation.get("multiplier", 100)))
                    )
                else:
                    value = None
                messages: list[str] = []
                status = "valid"
                if value is None:
                    status = "partial"
                    messages.append("One or more required calculation inputs are missing.")
                elif indicator["value_type"] == "count" and value < 0:
                    status = "warning"
                    messages.append("Calculated count is negative.")
                elif indicator["value_type"] == "percentage" and (value < 0 or value > 100):
                    status = "warning"
                    messages.append("Calculated percentage is outside 0-100.")
                record = {
                    "indicator_id": indicator["id"], "indicator_name": indicator["name"],
                    "period": period, "org_unit_id": org_unit_id,
                    "org_unit_name": unit.get("name"), "district": unit.get("district"),
                    "facility_code": unit.get("local_facility_code"),
                    "value": value, "value_type": indicator["value_type"],
                    "numerator": numerator, "denominator": denominator,
                    "source": "Malawi HMIS DHIS2", "validation_status": status,
                    "validation_messages": messages,
                }
                calculated[(indicator["id"], period, org_unit_id)] = record
                output.append(record)
    return output
