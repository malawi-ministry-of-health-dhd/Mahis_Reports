"""
Publish DHIS2-calculated indicators into MNID's aggregate store, under the same
schema/location mnid/aggregation/engine.py already produces for MAHIS routes
(data/mnid_aggregates/<route>/indicator_aggregates.parquet), so the existing
mnid/aggregation/store.py::get_aggregate() reads either source unmodified.

Reads credentials from config.py (bridged into the env vars mnid.dhis2.settings
expects) rather than requiring them to be exported by the caller's shell -- see
config.MNH_DHIS2_* for where those live.

Run once (or on a schedule): python -m mnid.dhis2.mnid_publish
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .calculations import calculate_indicators
from .client import DHIS2Client, parse_analytics_response
from .mappings import atomic_dx_values
from .periods import monthly_periods, period_start_date
from .sample_sync import _chunks, _selected_mapping
from .settings import DHIS2Settings
from .storage import atomic_json, atomic_parquet

_LOG = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# DHIS2 native indicator id -> MNID indicator id. Built from an exact label match
# between mnid/dhis2/config/indicators.json and mnid/aggregation/engine.py's loaded
# indicator set (see plan/session notes) -- 22 map onto pre-existing MNID
# indicators; 3 (Total/Fresh/Macerated births) were added as new MNID entries
# specifically for this (see scripts/add_dhis2_only_indicators.py).
DHIS2_TO_MNID_ID = {
    'live_births': 'mnid_lab_overview_004',
    'total_births': 'mnid_lab_core_totalbirths',
    'fresh_stillbirths': 'mnid_lab_core_freshstillbirths',
    'macerated_stillbirths': 'mnid_lab_core_maceratedstillbirths',
    'maternal_deaths': 'mnid_pnc_overview_004',
    'neonatal_deaths': 'mnid_nb_overview_002',
    'stillbirths': 'mnid_lab_overview_005',
    'anc_visits': 'mnid_anc_overview_001',
    'blood_pressure_measured': 'mnid_anc_prog_007',
    'tested_for_hiv': 'mnid_anc_prog_006',
    'screened_for_syphilis': 'mnid_anc_core_002',
    'at_least_4_anc_contacts': 'mnid_anc_prog_008',
    'tetanus_doses_2': 'mnid_anc_prog_004',
    'new_anc_registrations': 'mnid_anc_moh_002',
    'started_anc_in_first_trimester_0_12_weeks': 'mnid_anc_moh_011',
    'received_120_fefo_tablets': 'mnid_anc_moh_015',
    'received_itn_during_anc': 'mnid_anc_moh_016',
    'uterotonic_given_after_birth': 'mnid_lab_core_001',
    'newborns_not_breathing_at_birth_receiving_bag_mask_ventilation': 'mnid_lab_prog_012',
    'vitamin_k_at_birth': 'mnid_pnc_prog_011',
    'facility_deliveries': 'mnid_lab_prog_003',
    'delivered_at_this_facility': 'mnid_lab_moh_001',
    'delivered_at_home_or_in_transit': 'mnid_lab_moh_002',
    'delivered_by_skilled_attendant': 'mnid_lab_moh_005',
    'normal_vaginal_delivery': 'mnid_lab_moh_006',
}

# (label, category, target) for each MNID id above -- category drives which
# MNID tab (ANC/Labour/PNC/Newborn) an indicator appears under; the 3 DHIS2-only
# ones have no MAHIS definition to pull this from, so it's given here directly.
MNID_META = {
    'mnid_lab_overview_004': ('Live Births', 'Labour', 95),
    'mnid_lab_core_totalbirths': ('Total Births', 'Labour', 0),
    'mnid_lab_core_freshstillbirths': ('Fresh Stillbirths', 'Labour', 0),
    'mnid_lab_core_maceratedstillbirths': ('Macerated Stillbirths', 'Labour', 0),
    'mnid_pnc_overview_004': ('Maternal Deaths', 'PNC', 1),
    'mnid_nb_overview_002': ('Neonatal Deaths', 'Newborn', 5),
    'mnid_lab_overview_005': ('Stillbirths', 'Labour', 5),
    'mnid_anc_overview_001': ('ANC Visits', 'ANC', 80),
    'mnid_anc_prog_007': ('Blood pressure measured', 'ANC', 80),
    'mnid_anc_prog_006': ('Tested for HIV', 'ANC', 80),
    'mnid_anc_core_002': ('Screened for syphilis', 'ANC', 80),
    'mnid_anc_prog_008': ('At least 4 ANC contacts', 'ANC', 80),
    'mnid_anc_prog_004': ('Tetanus doses (2+)', 'ANC', 80),
    'mnid_anc_moh_002': ('New ANC registrations', 'ANC', 80),
    'mnid_anc_moh_011': ('Started ANC in first trimester (0-12 weeks)', 'ANC', 40),
    'mnid_anc_moh_015': ('Received 120+ FeFo tablets', 'ANC', 60),
    'mnid_anc_moh_016': ('Received ITN during ANC', 'ANC', 80),
    'mnid_lab_core_001': ('Uterotonic given after birth', 'Labour', 80),
    'mnid_lab_prog_012': ('Newborns not breathing at birth receiving bag-mask ventilation', 'Labour', 80),
    'mnid_pnc_prog_011': ('Vitamin K at birth', 'PNC', 80),
    'mnid_lab_prog_003': ('Facility deliveries', 'Labour', 80),
    'mnid_lab_moh_001': ('Delivered at this facility', 'Labour', 80),
    'mnid_lab_moh_002': ('Delivered at home or in transit', 'Labour', 5),
    'mnid_lab_moh_005': ('Delivered by skilled attendant', 'Labour', 80),
    'mnid_lab_moh_006': ('Normal vaginal delivery', 'Labour', 60),
}

DHIS2_ROUTE = 'dhis2'


def _bridge_credentials_from_config() -> None:
    """Populate MNH_DHIS2_* env vars from config.py if not already set in the
    environment. Keeps mnid.dhis2.settings env-only (per its own security
    posture) while letting config.py be this app's actual source of truth.
    """
    import config as cfg
    os.environ.setdefault('MNH_DHIS2_BASE_URL', getattr(cfg, 'MNH_DHIS2_BASE_URL', ''))
    os.environ.setdefault('MNH_DHIS2_USERNAME', getattr(cfg, 'MNH_DHIS2_USERNAME', ''))
    os.environ.setdefault('MNH_DHIS2_PASSWORD', getattr(cfg, 'MNH_DHIS2_PASSWORD', ''))


def publish_mnid_aggregate() -> dict:
    """Pull the working 25-indicator DHIS2 sample and publish it under MNID
    indicator ids into data/mnid_aggregates/dhis2/indicator_aggregates.parquet.
    """
    _bridge_credentials_from_config()
    settings = DHIS2Settings.from_env(require_credentials=True)
    periods = monthly_periods(settings.start_period, settings.end_period)
    mapping = _selected_mapping()
    requested_dx = atomic_dx_values(mapping)
    run_id = uuid.uuid4().hex

    values, rejected = [], []
    with DHIS2Client(settings) as client:
        for request_number, dx_batch in enumerate(_chunks(requested_dx, settings.dx_batch_size), 1):
            payload = client.analytics(
                dx_batch, periods, ['LEVEL-4'],
                sync_run_id=run_id, request_id=f'mnid-publish-{request_number:04d}',
            )
            parsed, batch_rejected = parse_analytics_response(payload)
            values.extend(parsed)
            rejected.extend(batch_rejected)
    if rejected:
        raise RuntimeError(f'Publish response contained {len(rejected)} rejected rows')

    org_units_path = Path(__file__).resolve().parent / 'config' / 'organisation_units.json'
    units = json.loads(org_units_path.read_text(encoding='utf-8'))['organisation_units']
    by_id = {u['org_unit_id']: u for u in units if u.get('level') == 'facility'}
    seen_unit_ids = sorted({v.org_unit_id for v in values})
    selected_units = [
        by_id.get(uid, {'org_unit_id': uid, 'name': uid, 'district': None, 'local_facility_code': None})
        for uid in seen_unit_ids
    ]

    atomic = {(v.dx, v.period, v.org_unit_id): Decimal(v.raw_value) for v in values}
    calculated = calculate_indicators(mapping, atomic, periods, selected_units)

    rows = []
    skipped_unmapped = 0
    for record in calculated:
        if record['value'] is None:
            continue
        dhis2_id = record['indicator_id']
        mnid_id = DHIS2_TO_MNID_ID.get(dhis2_id)
        if mnid_id is None:
            skipped_unmapped += 1
            continue
        label, category, target = MNID_META[mnid_id]
        value = float(record['value'])
        if record.get('value_type') == 'percentage' and record.get('numerator') is not None and record.get('denominator'):
            # true numerator/denominator pair (e.g. a screening rate)
            numerator = int(record['numerator'])
            denominator = int(record['denominator'])
            pct = round(min(numerator / denominator * 100, 100.0), 1) if denominator else 0.0
        else:
            # count-only indicator (e.g. Live Births): the count *is* the numerator,
            # denominator=numerator so it reads as "fully reported" rather than 0%.
            numerator = int(round(value))
            denominator = numerator
            pct = 100.0 if numerator else 0.0
        rows.append({
            'indicator_id': mnid_id,
            'indicator_label': label,
            'category': category,
            'target': target,
            'facility_code': record.get('facility_code') or '',
            'district': record.get('district') or '',
            'grain': 'monthly',
            'period_start': pd.Timestamp(period_start_date(record['period'])),
            'numerator': numerator,
            'denominator': denominator,
            'pct': pct,
        })

    out_dir = _PROJECT_ROOT / 'data' / 'mnid_aggregates' / DHIS2_ROUTE
    parquet_out = out_dir / 'indicator_aggregates.parquet'
    meta_out = out_dir / 'meta.json'

    # atomic_parquet/atomic_json (mnid/dhis2/storage.py) write to a temp file and
    # os.replace() into place -- matches the atomic-publish guarantee the rest of
    # this package relies on; a failed/partial run can't corrupt the last good file.
    atomic_parquet(parquet_out, rows)

    unique_indicators = {r['indicator_id'] for r in rows}
    unique_periods = {r['period_start'] for r in rows}
    unique_facility_codes = {r['facility_code'] for r in rows if r['facility_code']}
    meta = {
        'generated_at': datetime.utcnow().isoformat(),
        'rows': len(rows),
        'indicators': len(unique_indicators),
        'grains': ['monthly'],
        'data_source': 'dhis2',
        'use_demo_data': False,
        'last_run_status': 'ok',
        'sync_run_id': run_id,
        'mapping_version': mapping.get('mapping_version'),
        'period_start': settings.start_period,
        'period_end': settings.end_period,
        'skipped_unmapped_dhis2_indicators': skipped_unmapped,
    }
    atomic_json(meta_out, meta)

    return {
        'rows': len(rows),
        'mnid_indicators': len(unique_indicators),
        'periods': len(unique_periods),
        'facilities_with_code': len(unique_facility_codes),
        'output': str(parquet_out),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    result = publish_mnid_aggregate()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
