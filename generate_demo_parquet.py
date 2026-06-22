"""
Generate synthetic MNID demo data for demo_parquet/.
Creates richer MNH event patterns so the Country Profile renders non-zero
births, stillbirths, deaths, and complication trends across multiple scenarios.
Run: python generate_demo_parquet.py
"""
import calendar
import random
from datetime import date

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

# Month tag -> (year, month, days to generate). Spans from January of last year
# through today's month, so the data never goes stale relative to whenever this
# script gets run again - the current month is partial, up to today's day.
def _build_months(today: date) -> list[tuple[str, int, int, int]]:
    months = []
    year, month = today.year - 1, 1
    while (year, month) <= (today.year, today.month):
        days_in_month = calendar.monthrange(year, month)[1]
        last_day = today.day if (year, month) == (today.year, today.month) else days_in_month
        months.append((f"{year}{month:02d}", year, month, last_day))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return months


MONTHS = _build_months(date.today())

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


# Per-indicator base coverage rates (deliberately spread across the red/amber/green
# bands instead of one shared `rate` for every concept, which previously made every
# indicator converge on ~28-31%). Each facility gets a small jitter applied uniformly
# across all of these, so the *ranking* of indicators stays stable per facility while
# the absolute numbers still vary facility-to-facility.
RATES = {
    "anemia": 0.82, "hiv_test": 0.55, "bp": 0.42, "syphilis": 0.24, "urine": 0.91,
    "ga": 0.68, "tetanus": 0.50, "preg_planned": 0.36, "danger_signs": 0.78,
    "lab_core": 0.46, "vitk_lab": 0.88, "breastfeeding_lab": 0.73,
    "cortico": 0.24, "caesarean": 0.34, "kmc_mgmt": 0.58,
    "pnc_core": 0.63, "mother_alive": 0.95, "baby_alive": 0.92,
    "bcg": 0.70, "hiv_pos": 0.18, "lbw": 0.32,
    "nb_core": 0.80, "ikmc": 0.62, "resus": 0.40, "thermal_ok": 0.86,
    "vitk_nb": 0.90, "eligible_resus_given": 0.48,
}


def _r(key: str, jitter: float) -> float:
    return max(0.02, min(0.98, RATES[key] + jitter))


SCENARIOS = [
    {
        "name": "baseline",
        "labour_volume": 1.0,
        "pnc_volume": 1.0,
        "newborn_volume": 1.0,
        "live_birth": 0.90,
        "fresh_stillbirth": 0.05,
        "macerated_stillbirth": 0.05,
        "maternal_death": 0.04,
        "neonatal_death": 0.08,
        "obstetric_weights": [0.10, 0.07, 0.08, 0.10, 0.65],
        "newborn_comp_weights": [0.12, 0.12, 0.10, 0.66],
        "maternal_sepsis": 0.10,
        "pph": 0.13,
        "ruptured_uterus": 0.04,
        "birth_asphyxia": 0.12,
        "neonatal_sepsis": 0.11,
    },
    {
        "name": "stillbirth_spike",
        "labour_volume": 1.1,
        "pnc_volume": 1.0,
        "newborn_volume": 0.95,
        "live_birth": 0.78,
        "fresh_stillbirth": 0.13,
        "macerated_stillbirth": 0.09,
        "maternal_death": 0.05,
        "neonatal_death": 0.10,
        "obstetric_weights": [0.12, 0.10, 0.11, 0.13, 0.54],
        "newborn_comp_weights": [0.18, 0.14, 0.11, 0.57],
        "maternal_sepsis": 0.12,
        "pph": 0.16,
        "ruptured_uterus": 0.07,
        "birth_asphyxia": 0.18,
        "neonatal_sepsis": 0.12,
    },
    {
        "name": "sepsis_pressure",
        "labour_volume": 1.0,
        "pnc_volume": 1.1,
        "newborn_volume": 1.15,
        "live_birth": 0.88,
        "fresh_stillbirth": 0.06,
        "macerated_stillbirth": 0.06,
        "maternal_death": 0.06,
        "neonatal_death": 0.16,
        "obstetric_weights": [0.11, 0.08, 0.08, 0.10, 0.63],
        "newborn_comp_weights": [0.10, 0.15, 0.24, 0.51],
        "maternal_sepsis": 0.20,
        "pph": 0.14,
        "ruptured_uterus": 0.05,
        "birth_asphyxia": 0.13,
        "neonatal_sepsis": 0.26,
    },
    {
        "name": "recovery",
        "labour_volume": 0.95,
        "pnc_volume": 0.95,
        "newborn_volume": 0.9,
        "live_birth": 0.94,
        "fresh_stillbirth": 0.03,
        "macerated_stillbirth": 0.03,
        "maternal_death": 0.02,
        "neonatal_death": 0.05,
        "obstetric_weights": [0.07, 0.04, 0.05, 0.07, 0.77],
        "newborn_comp_weights": [0.08, 0.08, 0.07, 0.77],
        "maternal_sepsis": 0.05,
        "pph": 0.08,
        "ruptured_uterus": 0.02,
        "birth_asphyxia": 0.08,
        "neonatal_sepsis": 0.08,
    },
]


def _scenario_for(fac_code: str, tag: str) -> dict:
    idx = (int(fac_code) + int(tag[-2:]) + int(tag[:4])) % len(SCENARIOS)
    return SCENARIOS[idx]


def _scaled_count(low: int, high: int, multiplier: float) -> int:
    return max(1, round(random.randint(low, high) * multiplier))


for district, facilities in DISTRICTS.items():
    for fac_name, fac_code in facilities:
        fac_jitter = random.uniform(-JITTER, JITTER)

        for tag, year, month, days in MONTHS:
            scenario = _scenario_for(fac_code, tag)
            # ── ANC ──────────────────────────────────────────────────────────
            anc_pids = [_next_id() for _ in range(random.randint(28, 42))]
            anc_sets = {key: _sample_n(anc_pids, _r(key, fac_jitter)) for key in [
                "anemia", "hiv_test", "bp", "syphilis", "urine", "ga", "tetanus",
                "preg_planned", "danger_signs",
            ]}

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

                if pid in anc_sets["anemia"]:
                    _obs(tmpl, "Anemia screening", "Yes")
                if pid in anc_sets["hiv_test"]:
                    _obs(tmpl, "HIV Test", "Negative")
                if pid in anc_sets["bp"]:
                    _obs(tmpl, "Systolic blood pressure", value_n=float(random.randint(100, 140)))
                    _obs(tmpl, "Diastolic blood pressure", value_n=float(random.randint(60, 90)))
                if pid in anc_sets["syphilis"]:
                    _obs(tmpl, "Syphilis Test Result", "Negative")
                if pid in anc_sets["urine"]:
                    _obs(tmpl, "Urine test status", "urine test conducted")
                if pid in anc_sets["ga"]:
                    _obs(tmpl, "Gestational age recorded", "GA by ultrasound")
                if pid in anc_sets["tetanus"]:
                    _obs(tmpl, "Number of tetanus doses", "two doses")
                if pid in anc_sets["preg_planned"]:
                    _obs(tmpl, "Pregnancy planned", "Yes")
                if pid in anc_sets["danger_signs"]:
                    _obs(tmpl, "Danger signs present", "Yes")

            # ── Labour ───────────────────────────────────────────────────────
            lab_pids = [_next_id() for _ in range(_scaled_count(10, 18, scenario["labour_volume"]))]
            num_lab = _sample_n(lab_pids, _r("lab_core", fac_jitter))
            vitk_lab_num = _sample_n(lab_pids, _r("vitk_lab", fac_jitter))
            breastfeeding_num = _sample_n(lab_pids, _r("breastfeeding_lab", fac_jitter))

            # Indicator-specific sub-denominators
            cortico_denom = _sample_n(lab_pids, 0.6)
            cortico_num = _sample_n(list(cortico_denom), _r("cortico", fac_jitter))
            mod_denom = _sample_n(lab_pids, 0.6)
            caesarean_num = _sample_n(list(mod_denom), _r("caesarean", fac_jitter))
            mgmt_denom = _sample_n(lab_pids, 0.6)
            kmc_num = _sample_n(list(mgmt_denom), _r("kmc_mgmt", fac_jitter))

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

                outcome = random.choices(
                    ["Live birth", "Fresh still birth", "Macerated still birth"],
                    weights=[
                        scenario["live_birth"],
                        scenario["fresh_stillbirth"],
                        scenario["macerated_stillbirth"],
                    ],
                    k=1,
                )[0]
                obstetric_comp = random.choices(
                    ["PPH", "Eclampsia", "Obstructed labour", "Preterm labour", "None"],
                    weights=scenario["obstetric_weights"],
                    k=1,
                )[0]
                newborn_comp = random.choices(
                    ["Birth asphyxia", "Prematurity", "Sepsis", "None"],
                    weights=scenario["newborn_comp_weights"],
                    k=1,
                )[0]

                # ~12% of deliveries are outborn (born outside this facility)
                _delivery_location = (
                    "This facility"
                    if random.random() > 0.12
                    else random.choice(["Home", "Referral facility", "Community"])
                )
                _obs(tmpl, "Place of delivery", _delivery_location)
                _obs(tmpl, "Outcome of the delivery", outcome)
                _obs(tmpl, "Obstetric complications", obstetric_comp)
                _obs(tmpl, "Newborn baby complications", newborn_comp)
                _obs(tmpl, "Estimated blood loss", value_n=float(random.randint(150, 700)))

                if pid in num_lab:
                    if random.random() < scenario["maternal_sepsis"] or obstetric_comp == "None":
                        _obs(tmpl, "Maternal sepsis", "Yes" if random.random() < scenario["maternal_sepsis"] else "No")
                    if random.random() < scenario["pph"] or obstetric_comp == "PPH":
                        _obs(tmpl, "PPH", "Yes")
                        _obs(tmpl, "Oxytocin 10 iu given", "Yes")
                        if random.random() < 0.72:
                            _obs(tmpl, "1g Tranexamic Acid IV slow push over 10 minutes", "Yes")
                        if random.random() < 0.55:
                            _obs(tmpl, "Misoprostol 800 micrograms", "Yes")
                    if random.random() < scenario["ruptured_uterus"]:
                        _obs(tmpl, "Obstetric complications", "Ruptured uterus")

                # Vitamin K and Breast feeding: recorded for ALL Labour patients
                # (denominator = all Labour), each with its own coverage rate.
                _obs(tmpl, "Vitamin K given", "Yes" if pid in vitk_lab_num else "No")
                _obs(tmpl, "Breast feeding", "Yes" if pid in breastfeeding_num else "No")

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
                        "KMC" if pid in kmc_num else (
                            "Antibiotics" if newborn_comp == "Sepsis"
                            else "Resuscitation" if newborn_comp == "Birth asphyxia"
                            else "Routine care"
                        ),
                    )

            # ── PNC ──────────────────────────────────────────────────────────
            pnc_pids = [_next_id() for _ in range(_scaled_count(8, 14, scenario["pnc_volume"]))]
            num_pnc = _sample_n(pnc_pids, _r("pnc_core", fac_jitter))

            mother_denom = _sample_n(pnc_pids, 0.85)
            mother_alive = _sample_n(list(mother_denom), max(0.02, 1 - scenario["maternal_death"]))
            baby_denom = _sample_n(pnc_pids, 0.85)
            baby_alive = _sample_n(list(baby_denom), max(0.02, 1 - scenario["neonatal_death"]))
            immun_denom = _sample_n(pnc_pids, 0.75)
            bcg_num = _sample_n(list(immun_denom), _r("bcg", fac_jitter))
            hiv_denom = _sample_n(pnc_pids, 0.70)
            hiv_pos = _sample_n(list(hiv_denom), _r("hiv_pos", fac_jitter))
            prematurity_denom = _sample_n(pnc_pids, 0.50)
            lbw_num = _sample_n(list(prematurity_denom), _r("lbw", fac_jitter))

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
            nb_pids = [_next_id() for _ in range(_scaled_count(5, 11, scenario["newborn_volume"]))]
            num_nb = _sample_n(nb_pids, _r("nb_core", fac_jitter))

            ikmc_denom = _sample_n(nb_pids, 0.55)
            ikmc_num = _sample_n(list(ikmc_denom), _r("ikmc", fac_jitter))
            resus_denom = _sample_n(nb_pids, 0.45)
            resus_num = _sample_n(list(resus_denom), _r("resus", fac_jitter))
            thermal_denom = _sample_n(nb_pids, 0.65)
            thermal_num = _sample_n(list(thermal_denom), _r("thermal_ok", fac_jitter))
            vitk_denom = _sample_n(nb_pids, 0.65)
            vitk_num = _sample_n(list(vitk_denom), _r("vitk_nb", fac_jitter))
            eligible_denom = _sample_n(nb_pids, 0.45)
            eligible_resus = _sample_n(list(eligible_denom), _r("eligible_resus_given", fac_jitter))
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
                    _obs(tmpl, "Admission outcome", "Died" if random.random() < scenario["neonatal_death"] else "Discharged")
                    if pid in cpap_1000_pids or pid in cpap_1500_pids:
                        _obs(tmpl, "CPAP support", "Bubble CPAP")
                    if random.random() < scenario["birth_asphyxia"]:
                        _obs(tmpl, "Birth asphyxia suspected", "Yes")
                    if random.random() < scenario["neonatal_sepsis"]:
                        _obs(tmpl, "Neonatal Sepsis - Early Onset", "Yes")

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
                if random.random() < scenario["neonatal_sepsis"]:
                    _obs(tmpl, "Parenteral antibiotics given", "Yes")

            # ── Operational readiness (facility-level, once per month) ─────────
            ready_pid, ready_enc = _next_id(), _next_id()
            ready_tmpl = _make_row(
                ready_pid, ready_enc, _rand_date(year, month, days),
                "ANC PROGRAM", "ANC PROGRAM",
                fac_name, fac_code, district,
                "ANC visit", "new", 30, "Female",
            )
            all_rows.append(ready_tmpl)
            _obs(ready_tmpl, "Essential medicine availability",
                 "All available" if random.random() < 0.74 else random.choice(["Partially available", "Stocked out"]))
            _obs(ready_tmpl, "EmONC competency assessed",
                 "Assessed" if random.random() < 0.81 else "Not assessed")
            _obs(ready_tmpl, "Record completeness",
                 "Complete" if random.random() < 0.88 else "Incomplete")
            _obs(ready_tmpl, "Data entered within 7 days",
                 "Yes" if random.random() < 0.83 else "No")


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
