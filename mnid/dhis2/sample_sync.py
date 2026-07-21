"""Refresh the complete mapped-indicator dataset used by the MNH HMIS dashboard."""

from __future__ import annotations

import json
import logging
import uuid
from decimal import Decimal
from pathlib import Path

from .calculations import calculate_indicators
from .client import DHIS2Client, parse_analytics_response
from .mappings import atomic_dx_values, load_indicator_mapping
from .periods import monthly_periods, period_start_date
from .settings import DHIS2Settings
from .storage import atomic_parquet

_LOG = logging.getLogger(__name__)
INDICATOR_GROUPS = {
    "Births and outcomes": (
        "live_births", "total_births", "fresh_stillbirths",
        "macerated_stillbirths", "maternal_deaths", "neonatal_deaths",
        "stillbirths",
    ),
    "Antenatal care": (
        "anc_visits", "blood_pressure_measured", "screened_for_anaemia", "tested_for_hiv",
        "screened_for_syphilis", "at_least_4_anc_contacts",
        "tetanus_doses_2", "new_anc_registrations",
        "started_anc_in_first_trimester_0_12_weeks",
        "received_120_fefo_tablets", "received_itn_during_anc",
        "women_with_imminent_preterm_birth_receiving_acs",
    ),
    "Delivery and newborn care": (
        "uterotonic_given_after_birth",
        "newborns_not_breathing_at_birth_receiving_bag_mask_ventilation",
        "vitamin_k_at_birth", "facility_deliveries",
        "delivered_at_this_facility", "delivered_at_home_or_in_transit",
        "delivered_by_skilled_attendant", "normal_vaginal_delivery",
        "early_initiation_of_breastfeeding_within_1_hour_of_birth",
    ),
    "Obstetric complications and signal functions": (
        "pre_eclampsia_eclampsia_receiving_magnesium_sulphate",
        "obstetric_complication_pph", "obstetric_complication_eclampsia",
        "obstetric_complication_obstructed_labour",
        "obstetric_complication_maternal_sepsis",
        "signal_parenteral_antibiotics", "signal_anticonvulsants_mgso4",
        "signal_oxytocics", "signal_manual_placenta_removal",
        "signal_mva_retained_products", "signal_assisted_vaginal_delivery",
        "signal_caesarean_section", "signal_blood_transfusion",
    ),
    "Postnatal care": (
        "mothers_with_postnatal_complications", "babies_with_postnatal_complications",
        "mothers_checked_within_7_days", "babies_checked_within_7_days",
        "mothers_checked_at_6_weeks", "babies_checked_at_6_weeks",
        "immediate_postpartum_family_planning", "hiv_positive_postnatal_mothers",
        "hiv_exposed_babies_on_art_prophylaxis", "babies_who_received_bcg",
        "babies_who_received_polio_0",
    ),
}
SELECTED_INDICATOR_IDS = tuple(
    indicator_id
    for indicator_ids in INDICATOR_GROUPS.values()
    for indicator_id in indicator_ids
)
INDICATOR_GROUP_BY_ID = {
    indicator_id: group
    for group, indicator_ids in INDICATOR_GROUPS.items()
    for indicator_id in indicator_ids
}


def _selected_mapping() -> dict:
    mapping = load_indicator_mapping()
    selected = set(SELECTED_INDICATOR_IDS)
    mapping["indicators"] = [
        indicator for indicator in mapping["indicators"]
        if indicator["id"] in selected
    ]
    found = {indicator["id"] for indicator in mapping["indicators"]}
    missing = selected - found
    if missing:
        raise RuntimeError(f"Missing configured HMIS indicators: {sorted(missing)}")
    return mapping


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def refresh_sample() -> dict:
    """Pull one level-homogeneous snapshot and publish every mapped indicator."""
    settings = DHIS2Settings.from_env(require_credentials=True)
    periods = monthly_periods(settings.start_period, settings.end_period)
    mapping = _selected_mapping()
    requested_dx = atomic_dx_values(mapping)
    run_id = uuid.uuid4().hex
    values = []
    rejected = []
    with DHIS2Client(settings) as client:
        for request_number, dx_batch in enumerate(
            _chunks(requested_dx, settings.dx_batch_size), 1
        ):
            payload = client.analytics(
                dx_batch, periods, ["LEVEL-4"],
                sync_run_id=run_id,
                request_id=f"mnh-hmis-{request_number:04d}",
            )
            parsed, batch_rejected = parse_analytics_response(payload)
            values.extend(parsed)
            rejected.extend(batch_rejected)
    if rejected:
        raise RuntimeError(f"Sample response contained {len(rejected)} rejected rows")

    config_path = Path(__file__).resolve().parent / "config" / "organisation_units.json"
    units = json.loads(config_path.read_text(encoding="utf-8"))["organisation_units"]
    by_id = {unit["org_unit_id"]: unit for unit in units if unit.get("level") == "facility"}
    seen_unit_ids = sorted({value.org_unit_id for value in values})
    selected_units = [
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
        for value in values
    }
    calculated = calculate_indicators(mapping, atomic, periods, selected_units)
    records = []
    for record in calculated:
        if record["value"] is None:
            continue
        record.update({
            "indicator_group": INDICATOR_GROUP_BY_ID[record["indicator_id"]],
            "period_start": period_start_date(record["period"]).isoformat(),
            "is_explicit_zero": record["value"] == 0,
            "mapping_version": mapping["mapping_version"],
            "sync_run_id": run_id,
        })
        records.append(record)

    output = settings.aggregate_data_dir / "hmis_test.parquet"
    atomic_parquet(output, records)
    return {
        "rows": len(records),
        "facilities": len({row["org_unit_id"] for row in records}),
        "periods": len({row["period"] for row in records}),
        "indicators": len({row["indicator_id"] for row in records}),
        "configured_indicators": len(SELECTED_INDICATOR_IDS),
        "requested_dx": len(requested_dx),
        "output": str(output),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    result = refresh_sample()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
