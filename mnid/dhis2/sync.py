"""Command-line entry point for explicit MNID DHIS2 synchronization."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from typing import Any

from .exceptions import DHIS2Error
from .ingestion import build_query_plan, query_plan_summary, run_ingestion
from .mappings import load_indicator_mapping, load_organisation_units
from .periods import monthly_periods
from .settings import DHIS2Settings
from .status import load_status, utc_now, write_status

_LOG = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-period")
    parser.add_argument("--end-period")
    parser.add_argument("--org-unit", action="append", default=[])
    parser.add_argument("--org-level", action="append", choices=("national", "zone", "district", "facility", "community"), default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-config", action="store_true")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    return parser


def _selected_units(units: list[dict[str, Any]], selected: list[str], levels: list[str] | None = None) -> list[dict[str, Any]]:
    enabled = [unit for unit in units if unit.get("enabled")]
    if levels:
        enabled = [unit for unit in enabled if unit.get("level") in set(levels)]
    if not selected:
        return enabled
    wanted = set(selected)
    result = [unit for unit in enabled if unit["org_unit_id"] in wanted]
    missing = wanted - {unit["org_unit_id"] for unit in result}
    if missing:
        from .exceptions import DHIS2ConfigurationError
        raise DHIS2ConfigurationError(f"Requested organisation units are not enabled: {', '.join(sorted(missing))}")
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = DHIS2Settings.from_env(require_credentials=not (args.dry_run or args.validate_config))
        mapping = load_indicator_mapping()
        org_config = load_organisation_units(require_enabled=True)
        units = _selected_units(org_config["organisation_units"], args.org_unit, args.org_level)
        start = args.start_period or settings.start_period
        end = args.end_period or settings.end_period
        periods = monthly_periods(start, end)
        plan = build_query_plan(mapping, units, periods, settings)
        summary = query_plan_summary(mapping, units, periods, plan, settings)
        if args.validate_config:
            print(json.dumps({"status": "valid", **summary}, indent=2))
            return 0
        if args.dry_run:
            print(json.dumps({"status": "dry_run", **summary}, indent=2))
            return 0

        previous = load_status(settings.status_dir)
        running = {
            "source": "Malawi HMIS DHIS2", "status": "running",
            "sync_run_id": uuid.uuid4().hex, "started_at": utc_now(),
            "start_period": start, "end_period": end, "period_count": len(periods),
            "organisation_unit_count": len(units), "requested_dx_count": summary["unique_dx_operands"],
            "request_count": len(plan), "published": False,
            "last_successful_sync": previous.get("last_successful_sync"),
            "mapping_version": mapping["mapping_version"], "error": None,
        }
        write_status(settings.status_dir, running)
        try:
            completed = run_ingestion(settings, mapping, units, periods)
        except Exception as exc:
            failed = {
                **running, "status": "failed", "completed_at": utc_now(),
                "published": False, "error": f"{type(exc).__name__}: {exc}",
                "last_successful_sync": previous.get("last_successful_sync"),
            }
            write_status(settings.status_dir, failed)
            raise
        write_status(settings.status_dir, completed)
        print(json.dumps(completed, indent=2))
        return 0
    except DHIS2Error as exc:
        _LOG.error("DHIS2 synchronization failed: %s", exc)
        return 2
    except Exception as exc:
        _LOG.exception("Unexpected DHIS2 synchronization failure: %s", type(exc).__name__)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
