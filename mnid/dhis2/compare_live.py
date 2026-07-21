"""Compare the cached HMIS dashboard snapshot with a fresh DHIS2 Analytics pull."""

from __future__ import annotations

import argparse
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .calculations import calculate_indicators
from .client import DHIS2Client, parse_analytics_response
from .mappings import atomic_dx_values
from .periods import monthly_periods
from .sample_sync import INDICATOR_GROUP_BY_ID, _chunks, _selected_mapping
from .settings import DHIS2Settings


def compare_live(start_period: str, end_period: str, output: Path | None = None) -> dict:
    """Return per-indicator cached-versus-live totals without publishing live data."""
    settings = DHIS2Settings.from_env(require_credentials=True)
    periods = monthly_periods(start_period, end_period)
    mapping = _selected_mapping()
    requested_dx = atomic_dx_values(mapping)
    run_id = uuid.uuid4().hex

    live_values = []
    rejected = []
    with DHIS2Client(settings) as client:
        for request_number, dx_batch in enumerate(
            _chunks(requested_dx, settings.dx_batch_size), 1
        ):
            payload = client.analytics(
                dx_batch,
                periods,
                ["LEVEL-4"],
                sync_run_id=run_id,
                request_id=f"hmis-compare-{request_number:04d}",
            )
            parsed, batch_rejected = parse_analytics_response(payload)
            live_values.extend(parsed)
            rejected.extend(batch_rejected)
    if rejected:
        raise RuntimeError(f"Live comparison rejected {len(rejected)} Analytics rows")

    units_path = Path(__file__).resolve().parent / "config" / "organisation_units.json"
    configured_units = json.loads(units_path.read_text(encoding="utf-8"))["organisation_units"]
    by_id = {
        unit["org_unit_id"]: unit
        for unit in configured_units
        if unit.get("level") == "facility"
    }
    seen_unit_ids = sorted({value.org_unit_id for value in live_values})
    live_units = [
        by_id.get(unit_id, {
            "org_unit_id": unit_id,
            "name": unit_id,
            "district": None,
            "local_facility_code": None,
        })
        for unit_id in seen_unit_ids
    ]
    atomic = {
        (value.dx, value.period, value.org_unit_id): Decimal(value.raw_value)
        for value in live_values
    }
    live_rows = pd.DataFrame(
        row for row in calculate_indicators(mapping, atomic, periods, live_units)
        if row["value"] is not None
    )
    if live_rows.empty:
        raise RuntimeError("Live comparison returned no calculated indicator values")
    live_rows["value"] = pd.to_numeric(live_rows["value"], errors="coerce")
    live_rows["indicator_group"] = live_rows["indicator_id"].map(INDICATOR_GROUP_BY_ID)

    snapshot_path = settings.aggregate_data_dir / "hmis_test.parquet"
    if not snapshot_path.exists():
        raise RuntimeError(f"Cached HMIS snapshot does not exist: {snapshot_path}")
    cached = pd.read_parquet(snapshot_path)
    cached["period"] = cached["period"].astype(str)
    cached["value"] = pd.to_numeric(cached["value"], errors="coerce")
    cached = cached[cached["period"].isin(periods)].copy()

    def aggregate(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
        totals = (
            frame.groupby(["indicator_id", "indicator_name"], as_index=False)["value"]
            .sum().rename(columns={"value": f"{prefix}_period_total"})
        )
        latest = (
            frame[frame["period"] == periods[-1]]
            .groupby("indicator_id", as_index=False)["value"]
            .sum().rename(columns={"value": f"{prefix}_latest_month"})
        )
        units = (
            frame.groupby("indicator_id", as_index=False)["org_unit_id"]
            .nunique().rename(columns={"org_unit_id": f"{prefix}_reporting_units"})
        )
        return totals.merge(latest, on="indicator_id", how="outer").merge(
            units, on="indicator_id", how="outer"
        )

    cached_summary = aggregate(cached, "cached")
    live_summary = aggregate(live_rows, "live")
    comparison = cached_summary.merge(
        live_summary,
        on=["indicator_id", "indicator_name"],
        how="outer",
    )
    comparison["indicator_group"] = comparison["indicator_id"].map(INDICATOR_GROUP_BY_ID)
    comparison["period_total_difference"] = (
        comparison["live_period_total"] - comparison["cached_period_total"]
    )
    comparison["latest_month_difference"] = (
        comparison["live_latest_month"] - comparison["cached_latest_month"]
    )
    comparison["period_total_matches"] = comparison["period_total_difference"].abs() < 1e-9
    comparison["latest_month_matches"] = comparison["latest_month_difference"].abs() < 1e-9
    comparison = comparison.sort_values(["indicator_group", "indicator_name"])

    output = output or (
        settings.normalized_data_dir
        / "comparisons"
        / f"hmis_{start_period}_{end_period}_{run_id[:8]}.csv"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(output, index=False)
    return {
        "status": "match" if (
            comparison["period_total_matches"].all()
            and comparison["latest_month_matches"].all()
        ) else "differences_found",
        "start_period": start_period,
        "end_period": end_period,
        "indicator_count": int(comparison["indicator_id"].nunique()),
        "requested_dx": len(requested_dx),
        "cached_rows": int(len(cached)),
        "live_calculated_rows": int(len(live_rows)),
        "cached_reporting_units": int(cached["org_unit_id"].nunique()),
        "live_reporting_units": int(live_rows["org_unit_id"].nunique()),
        "period_total_matches": int(comparison["period_total_matches"].sum()),
        "latest_month_matches": int(comparison["latest_month_matches"].sum()),
        "difference_count": int((
            ~comparison["period_total_matches"] | ~comparison["latest_month_matches"]
        ).sum()),
        "output": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-period", required=True, help="Inclusive YYYYMM period")
    parser.add_argument("--end-period", required=True, help="Inclusive YYYYMM period")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare_live(args.start_period, args.end_period, args.output)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "match" else 2


if __name__ == "__main__":
    raise SystemExit(main())
