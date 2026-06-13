"""
Syncs indicator JSON definitions with docs/indicator-status-overview.md.

Run: python scripts/sync_indicators_to_docs.py
"""
import json, glob, os

# ── UPDATES to existing indicators ────────────────────────────────────────────
UPDATES = {
    # Fix: was using HIV Test only, docs want composite (HIV+anaemia+BP)
    # Also fix duplicate with mnid_anc_extra_005 which uses same HIV Test filter
    'mnid_anc_004': {
        'label': 'HIV-tested and screened for anaemia and high blood pressure',
        'status': 'tracked',
        'note': 'Composite: ANC clients with HIV test, haemoglobin screening, and blood pressure all documented.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'ANC',
            'variable2': 'mnid_anc_hiv_anaemia_bp_screened', 'value2': 'Yes',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'ANC',
        },
    },
    # Fix label typo "received" → "receive" (docs use present tense)
    'mnid_nb_002': {
        'label': 'Eligible preterm and low birth-weight babies who receive iKMC',
    },
    # Fix: was awaiting_baseline with empty filters — data exists (12.2%)
    'mnid_nb_003': {
        'label': 'Babies between 1000-1499g who receive prophylactic CPAP',
        'status': 'tracked',
        'note': 'CPAP coverage among babies in 1000-1499g birth-weight band.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'mnid_newborn_cpap_1000_1499', 'value1': 'Yes',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'mnid_birth_weight_band', 'value1': '1000-1499g',
        },
    },
    # Fix: was awaiting_baseline with empty filters — data exists (10.6%)
    'mnid_nb_004': {
        'label': 'Eligible babies between 1500 and 1999g who receive CPAP',
        'status': 'tracked',
        'note': 'CPAP coverage among babies in 1500-1999g birth-weight band.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'mnid_newborn_cpap_1500_1999', 'value1': 'Yes',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'mnid_birth_weight_band', 'value1': '1500-1999g',
        },
    },
}

# ── NEW indicators to ADD per dashboard ───────────────────────────────────────
NEW_MATERNAL = [
    # ANC — missing from JSON, have data in demo
    {
        'id': 'mnid_anc_extra_006',
        'label': 'ANC visit documented',
        'category': 'ANC', 'target': 80, 'status': 'tracked',
        'note': 'Denominator: all ANC clients. Numerator: those with an ANC VISIT encounter recorded.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'ANC',
            'variable2': 'Encounter', 'value2': 'ANC VISIT',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'ANC',
        },
    },
    {
        'id': 'mnid_anc_extra_007',
        'label': 'ANC clients with blood pressure measured',
        'category': 'ANC', 'target': 80, 'status': 'tracked',
        'note': 'Clients with systolic or diastolic BP recorded in ANC.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'ANC',
            'variable2': 'mnid_anc_bp_screened', 'value2': 'Yes',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'ANC',
        },
    },
    # ANC — not in demo parquet (tracked in production)
    {
        'id': 'mnid_anc_extra_008',
        'label': 'ANC screened for syphilis',
        'category': 'ANC', 'target': 80, 'status': 'tracked',
        'note': 'Syphilis test concepts not present in the demo extract; shows 0% in demo, tracked in production.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'ANC',
            'variable2': 'mnid_anc_syphilis_tested', 'value2': 'Yes',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'ANC',
        },
    },
    {
        'id': 'mnid_anc_extra_009',
        'label': 'ANC clients with urinalysis performed',
        'category': 'ANC', 'target': 80, 'status': 'tracked',
        'note': 'Urinalysis concepts not present in the demo extract; shows 0% in demo, tracked in production.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'ANC',
            'variable2': 'mnid_anc_urinalysis_done', 'value2': 'Yes',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'ANC',
        },
    },
    # Labour — not in demo parquet (tracked in production)
    {
        'id': 'mnid_lab_extra_006',
        'label': 'Labour assessment documented',
        'category': 'Labour', 'target': 80, 'status': 'tracked',
        'note': 'Labour assessment encounter rows not present in the demo extract; shows 0% in demo, tracked in production.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'Labour',
            'variable2': 'mnid_labour_assessment_documented', 'value2': 'Yes',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'Labour',
        },
    },
    {
        'id': 'mnid_lab_extra_007',
        'label': 'Labour visit documented',
        'category': 'Labour', 'target': 80, 'status': 'tracked',
        'note': 'Labour and delivery visit encounter rows not present in the demo extract; shows 0% in demo, tracked in production.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'Labour',
            'variable2': 'mnid_labour_visit_documented', 'value2': 'Yes',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'Labour',
        },
    },
    {
        'id': 'mnid_lab_extra_008',
        'label': 'Estimated blood loss recorded after delivery',
        'category': 'Labour', 'target': 70, 'status': 'tracked',
        'note': 'Estimated blood loss concept not present in the demo extract; shows 0% in demo, tracked in production.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'Labour',
            'variable2': 'mnid_labour_estimated_blood_loss_recorded', 'value2': 'Yes',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'Labour',
        },
    },
    {
        'id': 'mnid_lab_extra_009',
        'label': 'Deliveries complicated by maternal sepsis',
        'category': 'Labour', 'target': 5, 'status': 'tracked',
        'note': 'Maternal sepsis concept not present in the demo extract; shows 0% in demo, tracked in production. Lower is better (burden indicator).',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'Labour',
            'variable2': 'mnid_labour_maternal_sepsis', 'value2': 'Yes',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'Labour',
        },
    },
]

NEW_NEWBORN = [
    {
        'id': 'mnid_nb_extra_008',
        'label': 'Neonatal enrolment documented',
        'category': 'Newborn', 'target': 80, 'status': 'tracked',
        'note': 'Proxy: Newborn clients with a NEONATAL CARE encounter recorded.',
        'numerator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'Newborn',
            'variable2': 'Encounter', 'value2': 'NEONATAL CARE',
        },
        'denominator_filters': {
            'unique': 'person_id',
            'variable1': 'Service_Area', 'value1': 'Newborn',
        },
    },
]


def apply_all(data):
    items = data if isinstance(data, list) else [data]
    for item in items:
        if item.get('dashboard_type') != 'mnid':
            continue

        inds = item.get('priority_indicators', [])
        ind_by_id = {i['id']: i for i in inds}
        rname = item.get('report_name', '')

        # Apply updates
        for iid, patch in UPDATES.items():
            if iid in ind_by_id:
                for k, v in patch.items():
                    ind_by_id[iid][k] = v
                print(f'  [UPDATE] {iid}')

        # Add new indicators
        adds = []
        if 'Maternal' in rname or 'Newborn' not in rname:
            adds = NEW_MATERNAL if 'Maternal' in rname else []
        if 'Newborn' in rname:
            adds = NEW_NEWBORN

        for new_ind in adds:
            if new_ind['id'] not in ind_by_id:
                inds.append(new_ind)
                ind_by_id[new_ind['id']] = new_ind
                print(f'  [ADD] {new_ind["id"]}: {new_ind["label"]}')
            else:
                print(f'  [SKIP-EXISTS] {new_ind["id"]}')

    return data


base = os.path.join(os.path.dirname(__file__), '..', 'data', 'visualizations')
json_files = [
    'validated_dashboard.json',
    'dashboards_duplicate.json',
    'validated_dashboard_harmonized_mahis.json',
]

for fname in json_files:
    path = os.path.join(base, fname)
    if not os.path.exists(path):
        print(f'SKIP (not found): {fname}')
        continue
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    print(f'\n=== {fname} ===')
    apply_all(data)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f'  Written.')

print('\nDone.')
