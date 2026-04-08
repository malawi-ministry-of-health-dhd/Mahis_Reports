"""
Generate MNID-aligned dummy MCH data for dashboard testing.

Covers indicator concepts used in the MNID MCH dashboard:
  - Coverage Trends
  - Clinical Analysis
  - Operational Readiness

Date range : 2024-01-01 → 2026-03-28
Output     : data/latest_data_opd.parquet  (merged — MCH rows appended)

Run from project root:
    python scripts/generate_mnid_dummy_data.py
"""
import os, random
import argparse
import numpy as np
import pandas as pd
from datetime import date, timedelta

random.seed(99)
np.random.seed(99)

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT     = os.path.join(ROOT, 'data', 'latest_data_opd.parquet')

START   = date(2024, 1, 1)
END     = date(2026, 3, 28)
DAYS    = (END - START).days + 1

# ── facility metadata ─────────────────────────────────────────────────────────
FACILITY_SPECS = [
    ('Mzimba',   'Mzimba District Hospital',              'District Hospital'),
    ('Mzimba',   'Ekwendeni Mission Hospital',            'Mission Hospital'),
    ('Mzimba',   'Embangweni Health Centre',              'Health Centre'),
    ('Karonga',  'Karonga District Hospital',             'District Hospital'),
    ('Karonga',  'Chilumba Rural Hospital',               'Rural Hospital'),
    ('Rumphi',   'Rumphi District Hospital',              'District Hospital'),
    ('Rumphi',   'Bolero Health Centre',                  'Health Centre'),
    ('Nkhata Bay','Nkhata Bay District Hospital',          'District Hospital'),
    ('Nkhata Bay','Mpamba Health Centre',                  'Health Centre'),
    ('Chitipa',  'Chitipa District Hospital',             'District Hospital'),
    ('Chitipa',  'Misuku Health Centre',                  'Health Centre'),
    ('Lilongwe', 'Kamuzu Central Hospital',               'Central Hospital'),
    ('Lilongwe', 'Bwaila District Hospital',              'District Hospital'),
    ('Lilongwe', 'Area 25 Health Centre',                 'Health Centre'),
    ('Lilongwe', 'Kawale Health Centre',                  'Health Centre'),
    ('Dedza',    'Dedza District Hospital',               'District Hospital'),
    ('Dedza',    'Mua Mission Hospital',                  'Mission Hospital'),
    ('Kasungu',  'Kasungu District Hospital',             'District Hospital'),
    ('Kasungu',  'Chulu Health Centre',                   'Health Centre'),
    ('Ntcheu',   'Ntcheu District Hospital',              'District Hospital'),
    ('Ntcheu',   'Bilira Health Centre',                  'Health Centre'),
    ('Salima',   'Salima District Hospital',              'District Hospital'),
    ('Salima',   'Lifuwu Health Centre',                  'Health Centre'),
    ('Blantyre', 'Queen Elizabeth Central Hospital',      'Central Hospital'),
    ('Blantyre', 'Chileka Health Centre',                 'Health Centre'),
    ('Blantyre', 'Ndirande Health Centre',                'Health Centre'),
    ('Zomba',    'Zomba Central Hospital',                'Central Hospital'),
    ('Zomba',    'Domasi Rural Hospital',                 'Rural Hospital'),
    ('Mangochi', 'Mangochi District Hospital',            'District Hospital'),
    ('Mangochi', 'Monkey Bay Community Hospital',         'Community Hospital'),
    ('Chikwawa', 'Chikwawa District Hospital',            'District Hospital'),
    ('Chikwawa', 'Ngabu Rural Hospital',                  'Rural Hospital'),
    ('Nsanje',   'Nsanje District Hospital',              'District Hospital'),
    ('Nsanje',   'Tengani Health Centre',                 'Health Centre'),
    ('Mzuzu',    'Mzuzu Urban Health Centre',             'Health Centre'),
    ('Lilongwe', 'Lilongwe Central Hospital',             'Central Hospital'),
    ('Blantyre', 'Blantyre South Health Centre',          'Health Centre'),
]

def _code_for(district, idx):
    initials = ''.join([p[0] for p in district.split()]).upper()
    return f"{initials}{idx:03d}"

FACILITIES = [
    (_code_for(d, i + 1), name, d, f"{d} TA", f"{d} Village")
    for i, (d, name, _typ) in enumerate(FACILITY_SPECS)
]

GIVEN_NAMES  = ['Grace','Mary','Ruth','Agnes','Mercy','Beatrice','Esther','Faith',
                'Joyce','Lydia','Alice','Rose','Anna','Janet','Sarah','Christine',
                'Martha','Edith','Lucy','Patricia','Gladys','Cecilia','Doris','Helena']
FAMILY_NAMES = ['Phiri','Banda','Mwale','Tembo','Chirwa','Gondwe','Mbewe','Njiru',
                'Lungu','Sakala','Mumba','Zulu','Dlamini','Nkosi','Mvula','Simwaka',
                'Kaunda','Malopa','Chipeta','Kalua','Manda','Ngwira','Mseka','Zimba']

USERS = [f'mch-user-{i:02d}' for i in range(1, 9)]

# per-facility encounter counts per day (mean, varies ±50% randomly)
ANC_PER_DAY     = 8
LABOUR_PER_DAY  = 3
PNC_PER_DAY     = 5
NEWBORN_PER_DAY = 2

# ── helpers ───────────────────────────────────────────────────────────────────
_enc_counter  = [200_000]
_pid_counter  = [1_000_000]

def next_enc_id():
    _enc_counter[0] += 1
    return _enc_counter[0]

def next_pid():
    _pid_counter[0] += 1
    return _pid_counter[0]

def rand_date():
    return START + timedelta(days=random.randint(0, DAYS - 1))

def rand_name():
    return random.choice(GIVEN_NAMES), random.choice(FAMILY_NAMES)

def weighted(choices, weights):
    return random.choices(choices, weights=weights, k=1)[0]

def base_row(pid, enc_id, d, prog, enc, concept, value, fac_tuple,
             gender='Female', age=None, value_n=None):
    fc, fn, dist, ta, vill = fac_tuple
    gn, fn_ = rand_name()
    age = int(age) if age is not None else random.randint(16, 42)
    age_group = 'Under 5' if age < 5 else 'Over 5'
    return {
        'person_id':    int(pid),
        'encounter_id': int(enc_id),
        'given_name':   gn,
        'family_name':  fn_,
        'Gender':       gender,
        'Age':          age,
        'Age_Group':    age_group,
        'Date':         pd.Timestamp(d),
        'Program':      prog,
        'Facility':     fn,
        'Facility_CODE':fc,
        'User':         random.choice(USERS),
        'District':     dist,
        'Encounter':    enc,
        'Home_district':dist,
        'TA':           ta,
        'Village':      vill,
        'visit_days':   int(random.randint(1, 90)),
        'obs_value_coded': value or '',
        'concept_name': concept,
        'Value':        value or '',
        'ValueN':       int(value_n) if value_n is not None else None,
        'DrugName':     '',
        'Value_name':   '',
        'new_revisit':  weighted(['New', 'Revisit'], [30, 70]),
        'Order_Name':   None,
        'count':        None,
        'count_set':    None,
        'sum':          None,
    }

# ── ANC rows for one encounter ─────────────────────────────────────────────────
def anc_encounter(pid, d, fac):
    enc_anc    = next_enc_id()
    enc_vitals = next_enc_id()
    enc_treat  = next_enc_id()
    age = random.randint(16, 42)
    rows = []

    P = 'ANC PROGRAM'
    ANC = 'ANC VISIT'
    VIT = 'VITALS'
    TRT = 'Treatment'

    # ANC screening indicators (aligned to MNID dashboard filters)
    rows.append(base_row(pid, enc_anc, d, P, ANC, 'Anemia screening',
                         weighted(['Screened', 'Not screened'], [85, 15]), fac, age=age))
    rows.append(base_row(pid, enc_anc, d, P, ANC, 'Infection screening',
                         weighted(['Screened', 'Not screened'], [82, 18]), fac, age=age))
    rows.append(base_row(pid, enc_anc, d, P, ANC, 'High blood pressure screening',
                         weighted(['Screened', 'Not screened'], [88, 12]), fac, age=age))

    # POCUS completed
    rows.append(base_row(pid, enc_anc, d, P, ANC, 'POCUS completed',
                         weighted(['Yes', 'No'], [70, 30]), fac, age=age))

    # HIV Test
    rows.append(base_row(pid, enc_anc, d, P, ANC, 'HIV Test',
                         weighted(['Non-reactive', 'Reactive'], [88, 12]), fac, age=age))

    # Number of tetanus doses (Value used by filters)
    tt = weighted(['two doses', 'three doses', 'four doses'], [55, 30, 15])
    rows.append(base_row(pid, enc_anc, d, P, ANC, 'Number of tetanus doses',
                         tt, fac, age=age, value_n=None))

    # Systolic Pressure* (VITALS) — numeric (kept for realism)
    sbp = round(random.gauss(118, 18))
    sbp = max(80, min(sbp, 170))
    rows.append(base_row(pid, enc_vitals, d, P, VIT, 'Systolic Pressure*',
                         str(sbp), fac, age=age, value_n=float(sbp)))

    return rows


# ── Labour rows for one encounter ─────────────────────────────────────────────
def labour_encounter(pid, d, fac):
    enc_ldv  = next_enc_id()   # LABOUR AND DELIVERY
    enc_sol  = next_enc_id()   # SUMMARY OF LABOUR
    enc_la   = next_enc_id()   # LABOUR ASSESSMENT
    age = random.randint(17, 42)
    rows = []

    P   = 'LABOUR AND DELIVERY PROGRAM'
    LDV = 'LABOUR AND DELIVERY'
    SOL = 'SUMMARY OF LABOUR'
    LA  = 'LABOUR ASSESSMENT'

    # Obstetric complications
    comp = weighted(
        ['None', 'post partum Haemorrhage', 'eclampsia',
         'sepsis', 'obstructed/Prolonged labour'],
        [55, 16, 8, 10, 11])
    rows.append(base_row(pid, enc_ldv, d, P, LDV, 'Obstetric complications', comp, fac, age=age))

    # Place of delivery
    place = weighted(['This facility', 'Home', 'Referral facility'], [82, 12, 6])
    rows.append(base_row(pid, enc_ldv, d, P, LDV, 'Place of delivery', place, fac, age=age))

    # Staff conducting delivery
    staff = weighted(['Midwife', 'Clinical officer', 'Nurse'], [58, 27, 15])
    rows.append(base_row(pid, enc_ldv, d, P, LDV, 'Staff conducting delivery', staff, fac, age=age))

    # Mode of delivery
    mode = weighted(['Vaginal delivery', 'Caesarean section'], [73, 27])
    rows.append(base_row(pid, enc_ldv, d, P, LDV, 'Mode of delivery', mode, fac, age=age))

    # Outcome of delivery
    outcome = weighted(['Live births', 'Fresh stillbirth', 'Macerated stillbirth'], [88, 8, 4])
    rows.append(base_row(pid, enc_ldv, d, P, LDV, 'Outcome of the delivery', outcome, fac, age=age))

    # Guideline-aligned care indicators
    rows.append(base_row(pid, enc_sol, d, P, SOL, 'Antenatal corticosteroids given',
                         weighted(['Yes', 'No'], [62, 38]), fac, age=age))
    rows.append(base_row(pid, enc_sol, d, P, SOL, 'Prophylactic azithromycin given',
                         weighted(['Yes', 'No'], [58, 42]), fac, age=age))
    rows.append(base_row(pid, enc_sol, d, P, SOL, 'PPH treatment bundle',
                         weighted(['Completed', 'Partial', 'Not required'], [55, 25, 20]), fac, age=age))
    rows.append(base_row(pid, enc_la, d, P, LA, 'Digital intrapartum monitoring',
                         weighted(['Used', 'Not used'], [64, 36]), fac, age=age))

    return rows


# ── PNC rows for one encounter ─────────────────────────────────────────────────
def pnc_encounter(pid, d, fac):
    enc_c  = next_enc_id()   # POSTNATAL CARE
    age = random.randint(16, 42)
    rows = []

    P   = 'PNC PROGRAM'
    PNC = 'POSTNATAL CARE'

    # Postnatal check period (COUNSELING)
    period = weighted(
        ['Up to 48 hrs or before discharge', '3-7 days', '8-42 days', '>6 weeks'],
        [45, 28, 18, 9])
    rows.append(base_row(pid, enc_c, d, P, PNC, 'Postnatal check period', period, fac, age=age))

    # Postnatal complications
    pncc = weighted(['None', 'Sepsis', 'Postpartum hemorrhage'], [78, 12, 10])
    rows.append(base_row(pid, enc_c, d, P, PNC, 'Postnatal complications', pncc, fac, age=age))

    # Mother HIV Status
    hiv_s = weighted(['Negative', 'Positive'], [83, 17])
    rows.append(base_row(pid, enc_c, d, P, PNC, 'Mother HIV Status', hiv_s, fac, age=age))

    # Breast feeding
    bf = weighted(['Exclusive', 'exclusive breastfeeding', 'Mixed', 'Not breastfeeding'], [55, 10, 20, 15])
    rows.append(base_row(pid, enc_c, d, P, PNC, 'Breast feeding', bf, fac, age=age))

    # Mother/baby final status
    m_status = weighted(['Stable', 'Referred', 'Death'], [86, 10, 4])
    rows.append(base_row(pid, enc_c, d, P, PNC, 'Status of the mother', m_status, fac, age=age))
    b_status = weighted(['Stable', 'Referred', 'Died'], [88, 8, 4])
    rows.append(base_row(pid, enc_c, d, P, PNC, 'Status of baby', b_status, fac, age=0))

    # Immunisation (both concepts used in indicators)
    imm = weighted(['BCG', 'bcg', 'Polio 0', 'None'], [60, 10, 20, 10])
    rows.append(base_row(pid, enc_c, d, P, PNC, 'Type of immunization the baby received', imm, fac, age=0))
    rows.append(base_row(pid, enc_c, d, P, PNC, 'Immunisation given', imm, fac, age=0))

    return rows


# ── Newborn rows for one encounter ────────────────────────────────────────────
def newborn_encounter(pid, d, fac):
    enc_nb = next_enc_id()
    rows = []
    age = random.randint(0, 1)
    gender = weighted(['Female', 'Male'], [50, 50])

    P   = 'PNC PROGRAM'
    NB  = 'NEONATAL CARE'

    # Thermal status on admission
    rows.append(base_row(pid, enc_nb, d, P, NB, 'Thermal status on admission',
                         weighted(['Not hypothermic', 'Mild hypothermia', 'Moderate hypothermia'],
                                  [70, 20, 10]), fac, age=age, gender=gender))

    # Eligible for neonatal resuscitation
    rows.append(base_row(pid, enc_nb, d, P, NB, 'Eligible for neonatal resuscitation',
                         weighted(['Yes', 'No'], [55, 45]), fac, age=age, gender=gender))

    # Neonatal resuscitation provided
    rows.append(base_row(pid, enc_nb, d, P, NB, 'Neonatal resuscitation provided',
                         weighted(['Yes', 'Stimulation only', 'Bag and mask', 'No'],
                                  [30, 20, 15, 35]), fac, age=age, gender=gender))

    # iKMC initiated
    rows.append(base_row(pid, enc_nb, d, P, NB, 'iKMC initiated',
                         weighted(['Yes', 'No', 'Not eligible'], [55, 30, 15]),
                         fac, age=age, gender=gender))

    # CPAP support
    rows.append(base_row(pid, enc_nb, d, P, NB, 'CPAP support',
                         weighted(['Bubble CPAP', 'Nasal oxygen', 'None'], [25, 30, 45]),
                         fac, age=age, gender=gender))

    # Phototherapy given
    rows.append(base_row(pid, enc_nb, d, P, NB, 'Phototherapy given',
                         weighted(['Yes', 'No'], [35, 65]), fac, age=age, gender=gender))

    # Parenteral antibiotics given
    rows.append(base_row(pid, enc_nb, d, P, NB, 'Parenteral antibiotics given',
                         weighted(['Yes', 'No'], [40, 60]), fac, age=age, gender=gender))

    # Newborn baby complications
    rows.append(base_row(pid, enc_nb, d, P, NB, 'Newborn baby complications',
                         weighted(['None', 'Sepsis', 'Respiratory distress', 'Jaundice'],
                                  [60, 15, 15, 10]), fac, age=age, gender=gender))

    return rows


# ── System readiness rows (monthly per facility) ─────────────────────────────-
def readiness_rows(d, fac):
    enc = next_enc_id()
    rows = []
    P   = 'MCH SYSTEM READINESS'
    ENC = 'SYSTEM READINESS'

    rows.append(base_row(next_pid(), enc, d, P, ENC, 'Essential medicine availability',
                         weighted(['All available', 'Not all available'], [70, 30]), fac, age=25))
    rows.append(base_row(next_pid(), enc, d, P, ENC, 'CPAP equipment status',
                         weighted(['Available', 'Not available'], [65, 35]), fac, age=25))
    rows.append(base_row(next_pid(), enc, d, P, ENC, 'Phototherapy unit status',
                         weighted(['Available', 'Not available'], [60, 40]), fac, age=25))
    rows.append(base_row(next_pid(), enc, d, P, ENC, 'Newborn resuscitation equipment status',
                         weighted(['Available', 'Not available'], [75, 25]), fac, age=25))

    rows.append(base_row(next_pid(), enc, d, P, ENC, 'EmONC competency assessed',
                         weighted(['Assessed', 'Not assessed'], [70, 30]), fac, age=25))
    rows.append(base_row(next_pid(), enc, d, P, ENC, 'SSNC competency assessed',
                         weighted(['Assessed', 'Not assessed'], [65, 35]), fac, age=25))

    rows.append(base_row(next_pid(), enc, d, P, ENC, 'Record completeness',
                         weighted(['Complete', 'Incomplete'], [80, 20]), fac, age=25))
    rows.append(base_row(next_pid(), enc, d, P, ENC, 'Data entered within 7 days',
                         weighted(['Yes', 'No'], [78, 22]), fac, age=25))

    return rows

def parse_args():
    parser = argparse.ArgumentParser(description="Generate MNID dummy data")
    parser.add_argument("--max-facilities", type=int, default=None,
                        help="Limit number of facilities included")
    parser.add_argument("--days", type=int, default=None,
                        help="Limit number of days from START (2024-01-01)")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="Scale encounter volume (e.g., 0.2 for 20%%)")
    return parser.parse_args()


def pick_facilities(max_facilities):
    if not max_facilities or max_facilities >= len(FACILITIES):
        return FACILITIES
    return random.sample(FACILITIES, k=max_facilities)


# ── build full dataset ────────────────────────────────────────────────────────
args = parse_args()

gen_days = DAYS if not args.days else max(1, min(args.days, DAYS))
end_date = START + timedelta(days=gen_days - 1)
scale = max(args.scale, 0.01)
facilities = pick_facilities(args.max_facilities)

print("Generating MNID dummy data …")
print(f"  Facilities: {len(facilities)} of {len(FACILITIES)}")
print(f"  Date range: {START} → {end_date}")
print(f"  Scale     : {scale}")

all_rows = []

for offset in range(gen_days):
    d = START + timedelta(days=offset)

    for fac in facilities:
        # ANC
        n_anc = max(1, int(np.random.poisson(ANC_PER_DAY * scale)))
        for _ in range(n_anc):
            all_rows.extend(anc_encounter(next_pid(), d, fac))

        # Labour
        n_lab = max(0, int(np.random.poisson(LABOUR_PER_DAY * scale)))
        for _ in range(n_lab):
            all_rows.extend(labour_encounter(next_pid(), d, fac))

        # PNC
        n_pnc = max(1, int(np.random.poisson(PNC_PER_DAY * scale)))
        for _ in range(n_pnc):
            all_rows.extend(pnc_encounter(next_pid(), d, fac))

        # Newborn
        n_nb = max(0, int(np.random.poisson(NEWBORN_PER_DAY * scale)))
        for _ in range(n_nb):
            all_rows.extend(newborn_encounter(next_pid(), d, fac))

        # System readiness (once per month per facility)
        if d.day == 1:
            all_rows.extend(readiness_rows(d, fac))

print(f"  Built {len(all_rows):,} observation rows.")

new_df = pd.DataFrame(all_rows)
new_df['Date'] = pd.to_datetime(new_df['Date'])

# Cast integer columns that must not be nullable object
new_df['person_id']    = new_df['person_id'].astype('Int64')
new_df['encounter_id'] = new_df['encounter_id'].astype('Int64')
new_df['Age']          = new_df['Age'].astype('Int64')
new_df['visit_days']   = new_df['visit_days'].astype('Int64')
new_df['ValueN']       = new_df['ValueN'].astype('Int64')   # nullable int — handles None

# ── merge with existing parquet ───────────────────────────────────────────────
if os.path.exists(OUT):
    existing = pd.read_parquet(OUT)
    # drop any old MCH rows so we don't duplicate
    existing = existing[~existing['Program'].isin(
        ['ANC PROGRAM', 'LABOUR AND DELIVERY PROGRAM', 'PNC PROGRAM']
    )]
    # cast existing integer columns to nullable Int64 to allow concat
    for col in ('person_id', 'encounter_id', 'Age', 'visit_days', 'ValueN'):
        if col in existing.columns:
            existing[col] = existing[col].astype('Int64')
    # align columns
    for col in existing.columns:
        if col not in new_df.columns:
            new_df[col] = None
    for col in new_df.columns:
        if col not in existing.columns:
            existing[col] = None
    combined = pd.concat([existing, new_df], ignore_index=True)
    print(f"  Merged with existing data → {len(combined):,} total rows.")
else:
    combined = new_df
    print("  No existing parquet found — writing standalone file.")

combined.to_parquet(OUT, index=False, engine='pyarrow')
print(f"\n✅  Saved to {OUT}")
print(f"   Date range : {new_df['Date'].min().date()} → {new_df['Date'].max().date()}")
print(f"   MCH rows   : {len(new_df):,}")
print("\nRow counts by Program:")
print(new_df['Program'].value_counts().to_string())
print("\nRow counts by concept_name:")
print(new_df['concept_name'].value_counts().to_string())
