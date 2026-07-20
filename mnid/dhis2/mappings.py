"""Load validated indicator and organisation-unit configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exceptions import DHIS2MappingError
from .schemas import _indicator_references, _iter_operands, validate_indicator_mapping, validate_organisation_units

CONFIG_DIR = Path(__file__).resolve().parent / "config"
DEFAULT_INDICATORS_PATH = CONFIG_DIR / "indicators.json"
DEFAULT_ORG_UNITS_PATH = CONFIG_DIR / "organisation_units.json"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DHIS2MappingError(f"Configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DHIS2MappingError(f"Invalid JSON in {path.name}: line {exc.lineno}") from exc
    if not isinstance(value, dict):
        raise DHIS2MappingError(f"{path.name} must contain a JSON object")
    return value


def load_indicator_mapping(path: Path = DEFAULT_INDICATORS_PATH) -> dict[str, Any]:
    return validate_indicator_mapping(_load(path))


def load_organisation_units(path: Path = DEFAULT_ORG_UNITS_PATH, *, require_enabled: bool = False) -> dict[str, Any]:
    return validate_organisation_units(_load(path), require_enabled=require_enabled)


def enabled_indicators(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in mapping["indicators"] if item.get("enabled")]


def atomic_dx_values(mapping: dict[str, Any]) -> list[str]:
    """Return sorted, unique atomic Analytics operands for enabled indicators."""
    values = {
        item["dx"]
        for indicator in enabled_indicators(mapping)
        for item in _iter_operands(indicator.get("calculation"))
    }
    return sorted(values)


def dependency_order(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """Return enabled indicators in deterministic dependency order."""
    by_id = {item["id"]: item for item in enabled_indicators(mapping)}
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    def visit(iid: str):
        if iid in seen:
            return
        for ref in _indicator_references(by_id[iid].get("calculation")):
            if ref in by_id:
                visit(ref)
        seen.add(iid)
        ordered.append(by_id[iid])
    for iid in sorted(by_id):
        visit(iid)
    return ordered
