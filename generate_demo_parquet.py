"""
Generate synthetic MNID demo data for demo_parquet/.
Covers 8 Malawi districts, Jan–Jun 2026, ~31% average indicator coverage.
Run once: python generate_demo_parquet.py
"""
import random
import numpy as np
import pandas as pd
from pathlib import Path

random.seed(42)
np.random.seed(42)

OUT_DIR = Path("demo_parquet")
OUT_DIR.mkdir(exist_ok=True)

# ── Geography ─────────────────────────────────────────────────────────────────
DISTRICTS = {
    "Lilongwe": [
        ("Kamuzu Central Hospital", "201"),
        ("Area 18 Health Centre", "202"),
        ("Kawale Health Centre", "203"),
    ],
    "Blantyre": [
        ("Queen Elizabeth Central Hospital", "301"),
        ("Ndirande Health Centre", "302"),
        ("Limbe Health Centre", "303"),
    ],
    "Zomba": [
        ("Zomba Central Hospital", "401"),
        ("Zomba Community HC", "402"),
    ],
    "Mzuzu": [
        ("Mzuzu Central Hospital", "501"),
        ("Mzimba Health Centre", "502"),
    ],
    "Dedza": [
        ("Dedza District Hospital", "601"),
        ("Dedza Health Centre", "602"),
    ],
    "Ntcheu": [
        ("Ntcheu District Hospital", "701"),
        ("Golomoti Health Centre", "702"),
    ],
    "Kasungu": [
        ("Kasungu District Hospital", "801"),
        ("Kasungu Health Centre", "802"),
    ],
    "Nkhata Bay": [
        ("Nkhata Bay District Hospital", "901"),
        ("Chintheche Health Centre", "902"),
    ],
}

# month tag → (year, month, days_in_month)
MONTHS = [
    ("202601", 2026, 1, 31),
    ("202602", 2026, 2, 28),
    ("202603", 2026, 3, 31),
    ("202604", 2026, 4, 30),
    ("202605", 2026, 5, 31),
    ("202606", 2026, 6, 11),  # partial month up to today
]

# Average coverage target ± per-facility jitter
BASE_RATE = 0.31
JITTER = 0.09

_id_seq = [0]


def _next_id() -> int:
    _id_seq[0] += 1
    return _id_seq[0]


def _rand_date(year: int, month: int, days: int) -> str:
    return f"{year}-{month:02d}-{random.randint(1, days):02d}"


def _age_group(age: int) -> str:
    if age < 5:
        return "Under 5"
    if age < 15:
        return "5-14"
    if age < 25:
        return "15-24"
    if age < 35:
        return "25-34"
    if age < 50:
        return "35-49"
    return "50+"


def _sample_n(population: list, rate: float) -> set:
    n = max(1, round(len(population) * rate))
    return set(random.sample(population, min(n, len(population))))


def _make_row(
    pid, enc_id, date_str, program, service_area, facility, fac_code,
    district, encounter, new_revisit, age, gender,
    concept=None, obs_coded=None, value=None, value_n=None,
) -> dict:
    return {
        "person_id": pid,
        "encounter_id": enc_id,
        "Date": date_str,
        "Program": program,
        "Service_Area": service_area,
        "Facility": facility,
        "Facility_CODE": fac_code,
        "District": district,
        "Encounter": encounter,
        "new_revisit": new_revisit,
        "Age": age,
        "Age_Group": _age_group(age),
        "Gender": gender,
        "Home_district": district,
        "TA": "",
        "Village": "",
        "concept_name": concept or "",
        "obs_value_coded": obs_coded or "",
        "Value": value or "",
        "ValueN": value_n,
        "visit_days": 1,
        "DrugName": "",
        "Value_name": "",
        "Order_Name": "",
        "count": 1,
        "count_set": 1,
        "sum": 1,
        "person_id_key": str(pid),
        "value_datetime": "",
        "months": date_str[:7],
        "User": "demo_user",
        "Reporting_Program": "",
        "Source_Program": "",
        "": "",
    }


all_rows: list[dict] = []


def _obs(template: dict, concept: str, obs_coded=None, value_n=None, encounter: str | None = None) -> None:
    row = dict(template)
    row["concept_name"] = concept or ""
    row["obs_value_coded"] = obs_coded or ""
    row["ValueN"] = value_n  # stays float/None — numeric column is fine
    if encounter is not None:
        row["Encounter"] = encounter
    all_rows.append(row)


for district, facilities in DISTRICTS.items():
    for fac_name, fac_code in facilities:
        rate = max(0.18, min(0.48, BASE_RATE + random.uniform(-JITTER, JITTER)))

        for tag, year, month, days in MONTHS:
            # ── ANC ──────────────────────────────────────────────────────────
            anc_pids = [_next_id() for _ in range(random.randint(28, 42))]
            num_anc = _sample_n(anc_pids, rate)

            for pid in anc_pids:
                enc_id = _next_id()
                dt = _rand_date(year, month, days)
                age = random.randint(15, 41)
                nr = "new" if random.random() < 0.3 else "revisit"
                tmpl = _make_row(
                    pid, enc_id, dt,
                    "ANC PROGRAM", "ANC PROGRAM",
                    fac_name, fac_code, district,
                    "ANC visit", nr, age, "Female",
                )
                all_rows.append(tmpl)  # base denominator row

                if pid in num_anc:
                    _obs(tmpl, "Anemia screening", "Yes")
                    _obs(tmpl, "HIV Test", "Negative")
                    _obs(tmpl, "Systolic blood pressure", value_n=float(random.randint(100, 140)))
                    _obs(tmpl, "Diastolic blood pressure", value_n=float(random.randint(60, 90)))
                    _obs(tmpl, "Syphilis Test Result", "Negative")
                    _obs(tmpl, "Urine test status", "urine test conducted")
                    _obs(tmpl, "Gestational age recorded", "GA by ultrasound")
                    _obs(tmpl, "Number of tetanus doses", "two doses")
                    _obs(tmpl, "Pregnancy planned", "Yes")
                    _obs(tmpl, "Danger signs present", "Yes")

            # ── Labour ───────────────────────────────────────────────────────
            lab_pids = [_next_id() for _ in range(random.randint(10, 18))]
            num_lab = _sample_n(lab_pids, rate)

            # Indicator-specific sub-denominators
            # corticosteroids: 60% have concept recorded, 31% of those = Yes
            cortico_denom = _sample_n(lab_pids, 0.6)
            cortico_num = _sample_n(list(cortico_denom), rate)
            # mode of delivery: reduce denom to ~rate so coverage ≈ 31%
            mod_denom = _sample_n(lab_pids, max(rate, 0.32))
            caesarean_num = _sample_n(list(mod_denom), rate)
            # newborn management: 60% have concept recorded, 31% = KMC
            mgmt_denom = _sample_n(lab_pids, 0.6)
            kmc_num = _sample_n(list(mgmt_denom), rate)

            for pid in lab_pids:
                enc_id = _next_id()
                dt = _rand_date(year, month, days)
                age = random.randint(16, 43)
                # Alternate encounter sources so computed flags fire
                enc = random.choice([
                    "Labour assessment",
                    "Labour assessment",
                    "Labour and delivery visit",
                ])
                tmpl = _make_row(
                    pid, enc_id, dt,
                    "LABOUR AND DELIVERY PROGRAM", "LABOUR AND DELIVERY PROGRAM",
                    fac_name, fac_code, district,
                    enc, "new", age, "Female",
                )
                all_rows.append(tmpl)

                if pid in num_lab:
                    _obs(tmpl, "Place of delivery", "This facility")
                    _obs(tmpl, "Maternal sepsis", "Yes")
                    _obs(tmpl, "Estimated blood loss", value_n=float(random.randint(150, 500)))

                # Vitamin K and Breast feeding: record for ALL Labour patients so
                # denominator (concept present) = all Labour → coverage = 31%
                _obs(tmpl, "Vitamin K given", "Yes" if pid in num_lab else "No")
                _obs(tmpl, "Breast feeding", "Yes" if pid in num_lab else "No")

                _obs(
                    tmpl, "Antenatal corticosteroids given",
                    "Yes" if pid in cortico_num else "No",
                ) if pid in cortico_denom else None

                if pid in mod_denom:
                    _obs(
                        tmpl, "Mode of delivery",
                        "Caesarean section" if pid in caesarean_num else "Normal vaginal delivery",
                    )

                if pid in mgmt_denom:
                    _obs(
                        tmpl, "Management given to newborn",
                        "KMC" if pid in kmc_num else "Routine care",
                    )

            # ── PNC ──────────────────────────────────────────────────────────
            pnc_pids = [_next_id() for _ in range(random.randint(8, 14))]
            num_pnc = _sample_n(pnc_pids, rate)

            mother_denom = _sample_n(pnc_pids, 0.85)
            mother_alive = _sample_n(list(mother_denom), rate)
            baby_denom = _sample_n(pnc_pids, 0.85)
            baby_alive = _sample_n(list(baby_denom), rate)
            immun_denom = _sample_n(pnc_pids, 0.75)
            bcg_num = _sample_n(list(immun_denom), rate)
            hiv_denom = _sample_n(pnc_pids, 0.70)
            hiv_pos = _sample_n(list(hiv_denom), rate)
            prematurity_denom = _sample_n(pnc_pids, 0.50)
            lbw_num = _sample_n(list(prematurity_denom), rate)

            for pid in pnc_pids:
                enc_id = _next_id()
                dt = _rand_date(year, month, days)
                age = random.randint(15, 40)
                tmpl = _make_row(
                    pid, enc_id, dt,
                    "PNC PROGRAM", "PNC PROGRAM",
                    fac_name, fac_code, district,
                    "Pnc visit", "new", age, "Female",
                )
                all_rows.append(tmpl)

                if pid in num_pnc:
                    _obs(tmpl, "Postnatal check period", "Up to 48 hrs or before discharge")

                if pid in mother_denom:
                    _obs(tmpl, "Status of the mother", "Alive" if pid in mother_alive else "Deceased")
                if pid in baby_denom:
                    _obs(tmpl, "Status of baby", "Alive" if pid in baby_alive else "Deceased")
                if pid in immun_denom:
                    _obs(tmpl, "Immunisation given", "BCG" if pid in bcg_num else "OPV")
                if pid in hiv_denom:
                    _obs(tmpl, "Mother HIV Status", "Positive" if pid in hiv_pos else "Negative")
                if pid in prematurity_denom:
                    _obs(tmpl, "Prematurity/Kangaroo", "Low birth weight" if pid in lbw_num else "Normal weight")

            # ── Newborn ───────────────────────────────────────────────────────
            nb_pids = [_next_id() for _ in range(random.randint(5, 11))]
            num_nb = _sample_n(nb_pids, rate)

            ikmc_denom = _sample_n(nb_pids, 0.55)
            ikmc_num = _sample_n(list(ikmc_denom), rate)
            resus_denom = _sample_n(nb_pids, 0.45)
            resus_num = _sample_n(list(resus_denom), rate)
            thermal_denom = _sample_n(nb_pids, 0.65)
            thermal_num = _sample_n(list(thermal_denom), rate)
            vitk_denom = _sample_n(nb_pids, 0.65)
            vitk_num = _sample_n(list(vitk_denom), rate)
            eligible_denom = _sample_n(nb_pids, 0.45)
            eligible_resus = _sample_n(list(eligible_denom), rate)
            # CPAP with birth-weight bands
            cpap_1000_pids = _sample_n(nb_pids, 0.12)
            cpap_1500_pids = _sample_n(nb_pids, 0.15)

            for pid in nb_pids:
                enc_id = _next_id()
                dt = _rand_date(year, month, days)
                tmpl = _make_row(
                    pid, enc_id, dt,
                    "NEONATAL PROGRAM", "NEONATAL PROGRAM",
                    fac_name, fac_code, district,
                    "Neonatal enrolment", "new", 0, "Female",
                )
                all_rows.append(tmpl)

                if pid in num_nb:
                    bw = (
                        random.uniform(1000, 1499) if pid in cpap_1000_pids
                        else random.uniform(1500, 1999) if pid in cpap_1500_pids
                        else random.uniform(2000, 3800)
                    )
                    _obs(tmpl, "Birth weight", value_n=round(bw, 1))
                    _obs(tmpl, "Gestation in weeks", value_n=float(random.randint(28, 42)))
                    _obs(tmpl, "thermal care", "Yes")
                    if pid in cpap_1000_pids or pid in cpap_1500_pids:
                        _obs(tmpl, "CPAP support", "Bubble CPAP")

                if pid in ikmc_denom:
                    _obs(tmpl, "iKMC initiated", "Yes" if pid in ikmc_num else "No")
                if pid in resus_denom:
                    _obs(tmpl, "Neonatal resuscitation provided", "Yes" if pid in resus_num else "No")
                if pid in thermal_denom:
                    _obs(tmpl, "Thermal status on admission",
                         "Not hypothermic" if pid in thermal_num else "Hypothermic")
                if pid in vitk_denom:
                    _obs(tmpl, "Vitamin K given", "Yes" if pid in vitk_num else "No")
                if pid in eligible_denom:
                    _obs(tmpl, "Eligible for neonatal resuscitation", "Yes")
                    _obs(tmpl, "Neonatal resuscitation provided",
                         "Yes" if pid in eligible_resus else "No")


# ── Compile and save ──────────────────────────────────────────────────────────
df = pd.DataFrame(all_rows)
df["Date"] = pd.to_datetime(df["Date"])

# Force string columns so parquet stores them as utf-8, not Int32/null
STR_COLS = [
    "person_id", "encounter_id", "Program", "Service_Area", "Facility",
    "Facility_CODE", "District", "Encounter", "new_revisit", "Gender",
    "Home_district", "TA", "Village", "concept_name", "obs_value_coded",
    "Value", "DrugName", "Value_name", "Order_Name", "person_id_key",
    "months", "User", "Reporting_Program", "Source_Program", "",
]
for col in STR_COLS:
    if col in df.columns:
        df[col] = df[col].astype(object)

saved = 0
for tag, year, month, _days in MONTHS:
    mask = (df["Date"].dt.year == year) & (df["Date"].dt.month == month)
    chunk = df[mask].copy()
    if chunk.empty:
        continue
    path = OUT_DIR / f"data_{tag}.parquet"
    chunk.to_parquet(path, index=False)
    print(f"  {path.name}: {len(chunk):,} rows  |  "
          f"{chunk['District'].nunique()} districts  |  "
          f"{chunk['Facility'].nunique()} facilities")
    saved += 1

print(f"\nWrote {saved} parquet files to {OUT_DIR}/")
print(f"Total rows: {len(df):,}")
print(f"Districts: {df['District'].nunique()}  Facilities: {df['Facility'].nunique()}")
print(f"MCH rows: {len(df[df['Program'].str.contains('ANC|LABOUR|PNC|NEONATAL', case=False, na=False)]):,}")
