"""Refresh the five-indicator local dataset used by the MNH HMIS test tab."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from .client import DHIS2Client, parse_analytics_response
from .periods import monthly_periods, period_start_date
from .settings import DHIS2Settings
from .storage import atomic_parquet

_LOG = logging.getLogger(__name__)
SAMPLE_INDICATORS = {
    "EVt2iC6Tn34": "Started ANC in first trimester",
    "gLN6hOgR6ra": "Received ITN during ANC",
    "zAvhV81SCLV": "New ANC registrations",
    "iBBnHx1Uf50": "Live births (HIV exposed, NVP started)",
    "WjHvEHMCyKo": "Maternal deaths",
}


def refresh_sample() -> dict:
    """Pull one level-homogeneous sample and atomically publish local Parquet."""
    settings = DHIS2Settings.from_env(require_credentials=True)
    periods = monthly_periods(settings.start_period, settings.end_period)
    run_id = uuid.uuid4().hex
    with DHIS2Client(settings) as client:
        payload = client.analytics(
            list(SAMPLE_INDICATORS), periods, ["LEVEL-4"],
            sync_run_id=run_id, request_id="mnh-hmis-test-0001",
        )
    values, rejected = parse_analytics_response(payload)
    if rejected:
        raise RuntimeError(f"Sample response contained {len(rejected)} rejected rows")
    config_path = Path(__file__).resolve().parent / "config" / "organisation_units.json"
    units = json.loads(config_path.read_text(encoding="utf-8"))["organisation_units"]
    by_id = {unit["org_unit_id"]: unit for unit in units if unit.get("level") == "facility"}
    records = []
    for value in values:
        unit = by_id.get(value.org_unit_id, {})
        records.append({
            "indicator_id": value.dx, "indicator_name": SAMPLE_INDICATORS[value.dx],
            "period": value.period, "period_start": period_start_date(value.period).isoformat(),
            "org_unit_id": value.org_unit_id,
            "org_unit_name": unit.get("name", value.org_unit_id),
            "district": unit.get("district"),
            "facility_code": unit.get("local_facility_code"),
            "value": value.value, "is_explicit_zero": value.value == 0,
            "source": "Malawi HMIS DHIS2", "mapping_version": "2026-07-20",
            "sync_run_id": run_id,
        })
    output = settings.aggregate_data_dir / "hmis_test.parquet"
    atomic_parquet(output, records)
    return {
        "rows": len(records), "facilities": len({row["org_unit_id"] for row in records}),
        "periods": len({row["period"] for row in records}), "indicators": len(SAMPLE_INDICATORS),
        "output": str(output),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    result = refresh_sample()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
