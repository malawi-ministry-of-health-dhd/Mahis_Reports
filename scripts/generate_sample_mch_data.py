"""
Generate sample MCH / MNID parquet data for dashboard testing.
Merges into the existing latest_data_opd.parquet (or creates it if missing).

Run from project root:
    python scripts/generate_sample_mch_data.py
"""
import pandas as pd
import numpy as np
import os
import random
from datetime import date, timedelta

random.seed(42)
np.random.seed(42)

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT        = os.path.join(ROOT, 'data', 'sample_mch_data.parquet')   # standalone test file
OUT_MERGED = os.path.join(ROOT, 'data', 'latest_data_opd.parquet')   # real file (merge only if types match)

FACILITY_CODE = 'LL040033'
FACILITY_NAME = 'Lilongwe Central'
N_PERSONS     = 120          # unique MCH clients
START_DATE    = date(2025, 1, 1)
END_DATE      = date(2026, 3, 24)


def rand_dates(n, start=START_DATE, end=END_DATE):
    span = (end - start).days
    return [start + timedelta(days=random.randint(0, span)) for _ in range(n)]


def sample_persons(n):
    return [f'P{1000 + i}' for i in range(n)]


def build_anc_rows(persons):
    rows = []
    for pid in persons:
        d = rand_dates(1)[0]

        # ANC VISIT row — Reason for visit
        rows.append(dict(
            person_id=pid, encounter_id=f'E_anc_{pid}', Date=d,
            Program='ANC PROGRAM', Encounter='ANC VISIT',
            concept_name='Reason for visit',
            obs_value_coded=random.choice(['Scheduled ANC visit','First ANC contact']),
            Value='', ValueN=None,
            Gender=random.choice(['Female']),
            Age=random.randint(15, 42), Age_Group='Over 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit=random.choice(['New','Revisit']),
            HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # Tetanus doses — ~85% have 2+ doses
        if random.random() < 0.85:
            rows.append(dict(
                person_id=pid, encounter_id=f'E_tt_{pid}', Date=d,
                Program='ANC PROGRAM', Encounter='ANC VISIT',
                concept_name='Number of tetanus doses',
                obs_value_coded=random.choice(['two doses','three doses','four doses']),
                Value=random.choice(['two doses','three doses','four doses']),
                ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
                Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
                new_revisit='Revisit', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
                DrugName='', ValueName='',
            ))

        # HIV Test — ~90% tested
        if random.random() < 0.90:
            rows.append(dict(
                person_id=pid, encounter_id=f'E_hiv_{pid}', Date=d,
                Program='ANC PROGRAM', Encounter='ANC VISIT',
                concept_name='HIV Test',
                obs_value_coded=random.choice(['Non-reactive','Reactive']),
                Value=random.choice(['Non-reactive','Reactive']),
                ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
                Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
                new_revisit='Revisit', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
                DrugName='', ValueName='',
            ))

        # Pregnancy planned
        rows.append(dict(
            person_id=pid, encounter_id=f'E_pp_{pid}', Date=d,
            Program='ANC PROGRAM', Encounter='ANC VISIT',
            concept_name='Pregnancy planned',
            obs_value_coded=random.choice(['Yes','No']),
            Value=random.choice(['Yes','No']), ValueN=None,
            Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

    return rows


def build_labour_rows(persons):
    rows = []
    # Use a subset — not everyone delivers in the period
    delivering = persons[:80]
    for pid in delivering:
        d = rand_dates(1)[0]

        # Place of delivery — 80% facility
        place = 'This facility' if random.random() < 0.80 else random.choice(['Home','Referral facility'])
        rows.append(dict(
            person_id=pid, encounter_id=f'E_pl_{pid}', Date=d,
            Program='LABOUR AND DELIVERY PROGRAM', Encounter='LABOUR AND DELIVERY VISIT',
            concept_name='Place of delivery', obs_value_coded=place, Value=place,
            ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # Mode of delivery
        mode = random.choice(['Spontaneous vertex delivery','Caesarean section','Caesarean section',
                               'Assisted vaginal delivery'])
        rows.append(dict(
            person_id=pid, encounter_id=f'E_md_{pid}', Date=d,
            Program='LABOUR AND DELIVERY PROGRAM', Encounter='LABOUR AND DELIVERY VISIT',
            concept_name='Mode of delivery', obs_value_coded=mode, Value=mode,
            ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # Staff conducting delivery — ~85%
        if random.random() < 0.85:
            staff = random.choice(['Midwife','Clinical officer','Nurse'])
            rows.append(dict(
                person_id=pid, encounter_id=f'E_st_{pid}', Date=d,
                Program='LABOUR AND DELIVERY PROGRAM', Encounter='LABOUR AND DELIVERY VISIT',
                concept_name='Staff conducting delivery', obs_value_coded=staff, Value=staff,
                ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
                Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
                new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
                DrugName='', ValueName='',
            ))

        # Obstetric complications
        comp = random.choice(['None','None','None','Antepartum hemorrhage','Pre-eclampsia','Prolonged labour'])
        rows.append(dict(
            person_id=pid, encounter_id=f'E_oc_{pid}', Date=d,
            Program='LABOUR AND DELIVERY PROGRAM', Encounter='LABOUR AND DELIVERY VISIT',
            concept_name='Obstetric complications', obs_value_coded=comp, Value=comp,
            ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # Birth outcome
        outcome = random.choice(['Live births','Live births','Live births','Fresh stillbirth'])
        rows.append(dict(
            person_id=pid, encounter_id=f'E_bo_{pid}', Date=d,
            Program='LABOUR AND DELIVERY PROGRAM', Encounter='LABOUR AND DELIVERY VISIT',
            concept_name='Outcome of the delivery', obs_value_coded=outcome, Value=outcome,
            ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # Vitamin K at birth — 88%
        vk = 'Yes' if random.random() < 0.88 else 'No'
        rows.append(dict(
            person_id=pid, encounter_id=f'E_vk_{pid}', Date=d,
            Program='LABOUR AND DELIVERY PROGRAM', Encounter='IMMEDIATE POSTNATAL CHECKS CHILD',
            concept_name='Vitamin K given', obs_value_coded=vk, Value=vk,
            ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Under 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # Referral reason (30% of cases)
        if random.random() < 0.30:
            reason = random.choice(['Foetal distress','Hypertension','Bleeding','Prolonged labour'])
            rows.append(dict(
                person_id=pid, encounter_id=f'E_ref_{pid}', Date=d,
                Program='LABOUR AND DELIVERY PROGRAM', Encounter='LABOUR AND DELIVERY VISIT',
                concept_name='referral reasons', obs_value_coded=reason, Value=reason,
                ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
                Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
                new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
                DrugName='', ValueName='',
            ))

    return rows


def build_pnc_rows(persons):
    rows = []
    pnc_persons = persons[:90]
    for pid in pnc_persons:
        d = rand_dates(1)[0]

        # PNC check period — 72% within 48 hours
        period = ('Up to 48 hrs or before discharge'
                  if random.random() < 0.72
                  else random.choice(['3-7 days','8-42 days','After 6 weeks']))
        rows.append(dict(
            person_id=pid, encounter_id=f'E_pnc_{pid}', Date=d,
            Program='PNC PROGRAM', Encounter='COUNSELING',
            concept_name='Postnatal check period', obs_value_coded=period, Value=period,
            ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # Mother final status
        m_status = random.choice(['Alive','Alive','Alive','Alive','Alive','Died','Referred'])
        rows.append(dict(
            person_id=pid, encounter_id=f'E_ms_{pid}', Date=d,
            Program='PNC PROGRAM', Encounter='COUNSELING',
            concept_name='Status of the mother', obs_value_coded=m_status, Value=m_status,
            ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # Baby final status
        b_status = random.choice(['Alive','Alive','Alive','Alive','Alive','Died','Referred'])
        rows.append(dict(
            person_id=pid, encounter_id=f'E_bs_{pid}', Date=d,
            Program='PNC PROGRAM', Encounter='COUNSELING',
            concept_name='Status of baby', obs_value_coded=b_status, Value=b_status,
            ValueN=None, Gender='Female', Age=0, Age_Group='Under 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # BCG immunisation — 88%
        if random.random() < 0.88:
            rows.append(dict(
                person_id=pid, encounter_id=f'E_bcg_{pid}', Date=d,
                Program='PNC PROGRAM', Encounter='COUNSELING',
                concept_name='Immunisation given', obs_value_coded='BCG', Value='BCG',
                ValueN=None, Gender='Female', Age=0, Age_Group='Under 5',
                Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
                new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
                DrugName='', ValueName='',
            ))

        # Mother HIV status
        hiv_s = random.choice(['Negative','Negative','Negative','Positive','Reactive'])
        rows.append(dict(
            person_id=pid, encounter_id=f'E_mhiv_{pid}', Date=d,
            Program='PNC PROGRAM', Encounter='COUNSELING',
            concept_name='Mother HIV Status', obs_value_coded=hiv_s, Value=hiv_s,
            ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # Postnatal complications
        comp = random.choice(['None','None','Sepsis','Postpartum hemorrhage','Pre-eclampsia'])
        rows.append(dict(
            person_id=pid, encounter_id=f'E_pncc_{pid}', Date=d,
            Program='PNC PROGRAM', Encounter='COUNSELING',
            concept_name='Postnatal complications', obs_value_coded=comp, Value=comp,
            ValueN=None, Gender='Female', Age=random.randint(15,42), Age_Group='Over 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

        # Breastfeeding
        bf = random.choice(['Exclusive','Exclusive','Mixed','Not breastfeeding'])
        rows.append(dict(
            person_id=pid, encounter_id=f'E_bf_{pid}', Date=d,
            Program='PNC PROGRAM', Encounter='COUNSELING',
            concept_name='Breast feeding', obs_value_coded=bf, Value=bf,
            ValueN=None, Gender='Female', Age=0, Age_Group='Under 5',
            Facility=FACILITY_NAME, FacilityCode=FACILITY_CODE,
            new_revisit='New', HomeDistrict='Lilongwe', TA='TA1', Village='Village A',
            DrugName='', ValueName='',
        ))

    return rows


# ── assemble & save ────────────────────────────────────────────────────────────

persons = sample_persons(N_PERSONS)
rows = (
    build_anc_rows(persons)
    + build_labour_rows(persons)
    + build_pnc_rows(persons)
)

new_df = pd.DataFrame(rows)
new_df['Date'] = pd.to_datetime(new_df['Date'])

# Rename columns to match config keys
col_map = {
    'FacilityCode': 'facility_code',
    'HomeDistrict': 'home_district',
    'DrugName':     'DrugName',
    'ValueName':    'ValueName',
}
# Ensure all expected columns exist using config names
new_df = new_df.rename(columns={
    'FacilityCode': 'facility_code',
    'HomeDistrict': 'home_district',
})

# Save standalone sample file (safe, no type conflicts)
new_df.to_parquet(OUT, index=False)
print(f"Saved {len(new_df)} sample MCH rows -> {OUT}")
print("\nRow counts by Program:")
print(new_df['Program'].value_counts().to_string())
print("\nRow counts by concept_name (top 15):")
print(new_df['concept_name'].value_counts().head(15).to_string())
