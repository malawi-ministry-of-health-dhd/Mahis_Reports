from __future__ import annotations

import argparse
import glob
import os
import random
import shutil
from datetime import datetime, timedelta

import pandas as pd


SEED = 20260530
SOURCE_DIR = os.path.join("data", "parquet")
OUTPUT_DIR = "demo_parquet"
START_DATE = "2026-04-15"
END_DATE = "2026-05-30"

MCH_PROGRAM = "MATERNAL AND CHILD HEALTH"
NEONATAL_PROGRAM = "NEONATAL PROGRAM"

# Broad but still lightweight demo footprint.
DEMO_FACILITIES = [
    {"Facility_CODE": "3001", "Facility": "Queen Elizabeth Central Hospital", "District": "Blantyre"},
    {"Facility_CODE": "3002", "Facility": "Mwaiwathu Private Hospital", "District": "Blantyre"},
    {"Facility_CODE": "3003", "Facility": "Ndirande Health Centre", "District": "Blantyre"},
    {"Facility_CODE": "3004", "Facility": "Ntcheu District Hospital", "District": "Ntcheu"},
    {"Facility_CODE": "3005", "Facility": "Bilira Health Centre", "District": "Ntcheu"},
    {"Facility_CODE": "3006", "Facility": "Dedza District Hospital", "District": "Dedza"},
    {"Facility_CODE": "3007", "Facility": "Mtakataka Health Centre", "District": "Dedza"},
    {"Facility_CODE": "3008", "Facility": "Mzuzu District Hospital", "District": "Mzimba"},
    {"Facility_CODE": "3009", "Facility": "Katoto Rural Hospital", "District": "Mzimba"},
    {"Facility_CODE": "3010", "Facility": "Chikwawa District Hospital", "District": "Chikwawa"},
    {"Facility_CODE": "3011", "Facility": "Ngabu Rural Hospital", "District": "Chikwawa"},
    {"Facility_CODE": "3012", "Facility": "Nsanje District Hospital", "District": "Nsanje"},
    {"Facility_CODE": "3013", "Facility": "Trinity Hospital", "District": "Nsanje"},
    {"Facility_CODE": "3014", "Facility": "Mulanje District Hospital", "District": "Mulanje"},
    {"Facility_CODE": "3015", "Facility": "Muloza Health Centre", "District": "Mulanje"},
    {"Facility_CODE": "3016", "Facility": "Zomba Central Hospital", "District": "Zomba"},
    {"Facility_CODE": "3017", "Facility": "Likangala Health Centre", "District": "Zomba"},
    {"Facility_CODE": "3018", "Facility": "Balaka District Hospital", "District": "Balaka"},
    {"Facility_CODE": "3019", "Facility": "Phalula Rural Hospital", "District": "Balaka"},
    {"Facility_CODE": "3020", "Facility": "Mangochi District Hospital", "District": "Mangochi"},
    {"Facility_CODE": "3021", "Facility": "Monkey Bay Community Hospital", "District": "Mangochi"},
    {"Facility_CODE": "3022", "Facility": "Salima District Hospital", "District": "Salima"},
    {"Facility_CODE": "3023", "Facility": "Lifuwu Health Centre", "District": "Salima"},
    {"Facility_CODE": "3024", "Facility": "Lilongwe District Hospital", "District": "Lilongwe"},
    {"Facility_CODE": "3025", "Facility": "Area 25 Health Centre", "District": "Lilongwe"},
    {"Facility_CODE": "3026", "Facility": "Bwaila Hospital", "District": "Lilongwe"},
]

SERVICE_DEFINITIONS = {
    "ANC": {
        "program": MCH_PROGRAM,
        "reporting_program": MCH_PROGRAM,
        "encounter": "ANC VISIT",
        "daily_range": (1, 3),
        "concepts": [
            ("Pregnancy planned", "coded", ["Yes", "No"], None),
            ("HIV Test", "coded", ["Negative", "Positive", "Reactive", "Not done"], None),
            ("Blood group rhesus factor", "coded", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+"], None),
            ("Insecticide treated net given", "value", ["Yes", "No"], None),
            ("Number of tetanus doses", "coded", ["one dose", "two doses", "three doses", "four doses"], None),
            ("Danger signs present", "coded", ["Yes", "No"], None),
            ("Anemia screening", "coded", ["Yes", "No"], None),
            ("High blood pressure screening", "coded", ["Yes", "No"], None),
            ("Systolic blood pressure", "numeric", None, (90, 170)),
            ("Diastolic blood pressure", "numeric", None, (50, 110)),
            ("Gestational age recorded", "coded", ["GA by LNMP", "GA by palpation", "GA by ultrasound"], None),
            ("POCUS completed", "coded", ["Yes", "No"], None),
            ("Gestation in weeks", "numeric", None, (12, 40)),
        ],
    },
    "Labour": {
        "program": MCH_PROGRAM,
        "reporting_program": MCH_PROGRAM,
        "encounter": "LABOUR AND DELIVERY",
        "daily_range": (1, 2),
        "concepts": [
            ("Place of delivery", "coded", ["This facility", "Home"], None),
            ("Mode of delivery", "coded", ["Spontaneous vertex delivery", "Caesarean section", "Assisted delivery"], None),
            ("Staff conducting delivery", "value", ["Midwife", "Nurse", "Clinical officer", "Doctor"], None),
            ("Vitamin K given", "coded", ["Yes", "No"], None),
            ("Breast feeding", "coded", ["Yes", "No", "Exclusive"], None),
            ("Outcome of the delivery", "coded", ["Live birth", "Fresh still birth", "Macerated still birth"], None),
            ("Obstetric complications", "coded", ["PPH", "Eclampsia", "Obstructed labour", "Preterm labour", "None"], None),
            ("Newborn baby complications", "coded", ["Birth asphyxia", "Prematurity", "Sepsis", "None"], None),
            ("Management given to newborn", "coded", ["Resuscitation", "Thermal care", "KMC", "Antibiotics"], None),
            ("Antenatal corticosteroids given", "coded", ["Yes", "No"], None),
            ("Digital intrapartum monitoring", "coded", ["Used", "Not used"], None),
            ("Prophylactic azithromycin given", "coded", ["Yes", "No"], None),
            ("PPH treatment bundle", "coded", ["Yes", "No"], None),
        ],
    },
    "PNC": {
        "program": MCH_PROGRAM,
        "reporting_program": MCH_PROGRAM,
        "encounter": "POSTNATAL CARE",
        "daily_range": (1, 3),
        "concepts": [
            ("Postnatal check period", "coded", ["Up to 48 hrs or before discharge", "3 to 7 days", "8 to 42 days"], None),
            ("Status of the mother", "coded", ["Alive", "Stable", "Admitted"], None),
            ("Status of baby", "coded", ["Alive", "Admitted", "Referred"], None),
            ("Mother HIV Status", "coded", ["Negative", "Positive", "Reactive"], None),
            ("Counselling on family planning", "coded", ["Yes", "No"], None),
            ("Postpartum family planning method", "coded", ["Implant", "Depo", "Condoms", "None"], None),
            ("Prematurity/Kangaroo", "coded", ["KMC", "No KMC", "Low birth weight"], None),
            ("Vitamin K given", "coded", ["Yes", "No"], None),
            ("Breast feeding", "coded", ["Exclusive", "Mixed", "No"], None),
            ("Postnatal complications", "coded", ["Sepsis", "Bleeding", "Hypertension", "None"], None),
            ("Immunisation given", "coded", ["BCG", "OPV", "None"], None),
        ],
    },
    "Newborn": {
        "program": NEONATAL_PROGRAM,
        "reporting_program": NEONATAL_PROGRAM,
        "encounter": "NEONATAL PROGRAM",
        "daily_range": (1, 2),
        "concepts": [
            ("Birth weight", "numeric", None, (1.0, 4.5)),
            ("Gestation in weeks", "numeric", None, (28, 40)),
            ("Vitamin K given", "coded", ["Yes", "No"], None),
            ("thermal care", "coded", ["Yes", "No"], None),
            ("iKMC initiated", "coded", ["Yes", "No"], None),
            ("CPAP support", "coded", ["Bubble CPAP", "Nasal oxygen", "No CPAP"], None),
            ("Phototherapy given", "coded", ["Yes", "No"], None),
            ("Parenteral antibiotics given", "coded", ["Yes", "No"], None),
            ("Thermal status on admission", "coded", ["Not hypothermic", "Hypothermic"], None),
            ("Neonatal resuscitation provided", "coded", ["Stimulation only", "Bag and mask", "Yes"], None),
            ("Eligible for neonatal resuscitation", "coded", ["Yes", "No"], None),
            ("Admission outcome", "coded", ["Discharged", "Admitted", "Referred"], None),
        ],
    },
}

CONCEPT_RULES = {
    "ANC": {
        "HIV Test": {"weights": [0.44, 0.06, 0.01, 0.49]},
        "Anemia screening": {"include_probability": 0.90, "weights": [0.82, 0.18]},
        "High blood pressure screening": {"include_probability": 0.92, "weights": [0.86, 0.14]},
        "Systolic blood pressure": {"include_probability": 0.84},
        "Diastolic blood pressure": {"include_probability": 0.84},
        "Gestational age recorded": {"include_probability": 0.88, "weights": [0.40, 0.24, 0.36]},
        "POCUS completed": {"weights": [0.34, 0.66]},
        "Danger signs present": {"weights": [0.18, 0.82]},
        "Pregnancy planned": {"weights": [0.52, 0.48]},
    },
    "Labour": {
        "Mode of delivery": {"weights": [0.60, 0.18, 0.22]},
        "Vitamin K given": {"weights": [0.88, 0.12]},
        "Breast feeding": {"weights": [0.24, 0.11, 0.65]},
        "Outcome of the delivery": {"weights": [0.90, 0.05, 0.05]},
        "Obstetric complications": {"weights": [0.09, 0.06, 0.08, 0.07, 0.70]},
        "Newborn baby complications": {"weights": [0.11, 0.10, 0.09, 0.70]},
        "Antenatal corticosteroids given": {"weights": [0.72, 0.28]},
        "Digital intrapartum monitoring": {"weights": [0.58, 0.42]},
        "Prophylactic azithromycin given": {"weights": [0.42, 0.58]},
        "PPH treatment bundle": {"weights": [0.61, 0.39]},
        "Management given to newborn": {"weights": [0.16, 0.26, 0.21, 0.37]},
    },
    "PNC": {
        "Status of the mother": {"weights": [0.72, 0.20, 0.08]},
        "Status of baby": {"weights": [0.69, 0.17, 0.14]},
        "Mother HIV Status": {"weights": [0.67, 0.19, 0.14]},
        "Counselling on family planning": {"weights": [0.78, 0.22]},
        "Immunisation given": {"weights": [0.31, 0.35, 0.34]},
        "Breast feeding": {"weights": [0.46, 0.29, 0.25]},
        "Prematurity/Kangaroo": {"weights": [0.29, 0.42, 0.29]},
    },
    "Newborn": {
        "Birth weight": {"include_probability": 0.97},
        "Gestation in weeks": {"include_probability": 0.93},
        "Vitamin K given": {"weights": [0.85, 0.15]},
        "thermal care": {"include_probability": 0.90, "weights": [0.74, 0.26]},
        "iKMC initiated": {"weights": [0.48, 0.52]},
        "CPAP support": {"weights": [0.13, 0.19, 0.68]},
        "Phototherapy given": {"weights": [0.22, 0.78]},
        "Parenteral antibiotics given": {"weights": [0.28, 0.72]},
        "Thermal status on admission": {"weights": [0.62, 0.38]},
        "Neonatal resuscitation provided": {"include_probability": 0.90, "weights": [0.27, 0.13, 0.60]},
        "Eligible for neonatal resuscitation": {"weights": [0.49, 0.51]},
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate demo MNID parquet data.")
    parser.add_argument("--source", default=SOURCE_DIR)
    parser.add_argument("--output", default=OUTPUT_DIR)
    parser.add_argument("--start-date", default=START_DATE)
    parser.add_argument("--end-date", default=END_DATE)
    return parser.parse_args()


def load_source_files(source_dir: str) -> list[str]:
    files = sorted(glob.glob(os.path.join(source_dir, "*.parquet")))
    if not files:
        raise FileNotFoundError(f"No parquet files found in {source_dir}")
    return files


def load_template_columns(source_files: list[str]) -> list[str]:
    df = pd.read_parquet(source_files[0])
    return df.columns.tolist()


def get_max_ids(source_files: list[str]) -> tuple[int, int, int]:
    person_max = 0
    encounter_max = 0
    visit_max = 0
    for file_path in source_files:
        df = pd.read_parquet(file_path, columns=["person_id", "encounter_id", "visit_id"])
        person_series = pd.to_numeric(df["person_id"], errors="coerce").dropna()
        encounter_series = pd.to_numeric(df["encounter_id"], errors="coerce").dropna()
        visit_series = pd.to_numeric(df["visit_id"], errors="coerce").dropna()
        person_max = max(person_max, int(person_series.max()) if not person_series.empty else 0)
        encounter_max = max(encounter_max, int(encounter_series.max()) if not encounter_series.empty else 0)
        visit_max = max(visit_max, int(visit_series.max()) if not visit_series.empty else 0)
    return person_max, encounter_max, visit_max


def make_birthdate(encounter_dt: datetime, age_years: int) -> datetime:
    return encounter_dt - timedelta(days=age_years * 365)


def make_base_row(columns: list[str], facility_meta: dict, service_area: str, encounter_dt: datetime,
                  person_id: int, encounter_id: int, visit_id: int, patient_idx: int) -> dict:
    gender = random.choice(["Female", "Female", "Female", "Male"])
    age = random.randint(15, 39) if service_area != "Newborn" else 0
    birthdate = make_birthdate(encounter_dt, age if age > 0 else 0)
    age_days = max(age * 365, 1 if service_area == "Newborn" else age * 365)
    row = {col: None for col in columns}
    program = SERVICE_DEFINITIONS[service_area]["program"]
    reporting_program = SERVICE_DEFINITIONS[service_area]["reporting_program"]
    encounter_name = SERVICE_DEFINITIONS[service_area]["encounter"]
    facility_code = str(facility_meta["Facility_CODE"])
    row.update({
        "person_id": person_id,
        "visit_id": visit_id,
        "date_started": encounter_dt,
        "date_stopped": encounter_dt + timedelta(hours=2),
        "identifier": f"DEMO-{person_id}",
        "patient_identifier_type": "Demo Identifier",
        "given_name": f"Demo{person_id}",
        "family_name": f"Patient{encounter_id}",
        "Gender": gender,
        "birthdate": birthdate,
        "AgeDays": age_days,
        "Age": float(age),
        "Age_Group": "Under 5" if age < 5 else "Over 5",
        "person_attribute_name": None,
        "person_attribute_type": None,
        "Home_district": facility_meta["District"],
        "TA": f"Demo TA {patient_idx % 6 + 1}",
        "Village": f"Demo Village {patient_idx % 10 + 1}",
        "encounter_id": encounter_id,
        "Encounter": encounter_name,
        "Date": encounter_dt,
        "location_id": facility_code,
        "creator": 1,
        "provider_id": 1,
        "Program": program,
        "obs_datetime": encounter_dt,
        "obs_group_id": None,
        "accession_number": None,
        "value_group_id": None,
        "value_boolean": None,
        "value_coded_name_id": None,
        "DrugName": None,
        "value_datetime": encounter_dt,
        "ValueN": None,
        "Value": None,
        "Order_Type": None,
        "Order_Name": None,
        "Source_Program": program,
        "Reporting_Program": reporting_program,
        "Service_Area": service_area,
        "new_revisit": random.choice(["New", "Revisit", "Revisit"]),
        "DrugUnits": None,
        "User": "demo.user",
        "Facility_CODE": facility_code,
        "Facility": facility_meta["Facility"],
        "District": facility_meta["District"],
        "month_key": encounter_dt.strftime("%Y%m"),
    })
    return row


def concept_value(concept_type: str, values: list[str] | None, numeric_range: tuple[float, float] | None):
    if concept_type == "coded":
        return random.choice(values or []), None, None
    if concept_type == "value":
        return None, random.choice(values or []), None
    if concept_type == "numeric":
        lower, upper = numeric_range or (0, 1)
        return None, None, round(random.uniform(lower, upper), 1)
    return None, None, None


def concept_rule(service_area: str, concept_name: str) -> dict:
    return CONCEPT_RULES.get(service_area, {}).get(concept_name, {})


def build_demo_rows(template_columns: list[str], person_start: int, encounter_start: int,
                    visit_start: int, start_date: str, end_date: str) -> tuple[dict[str, list[dict]], int]:
    rows_by_month: dict[str, list[dict]] = {}
    row_count = 0
    person_id = person_start
    encounter_id = encounter_start
    visit_id = visit_start
    start_dt = datetime.fromisoformat(start_date)
    end_dt = datetime.fromisoformat(end_date)
    day_count = (end_dt - start_dt).days + 1

    for facility_idx, facility_meta in enumerate(DEMO_FACILITIES):
        is_hospital = "Hospital" in facility_meta["Facility"]
        is_central = "Central Hospital" in facility_meta["Facility"]
        for day_offset in range(day_count):
            day_dt = start_dt + timedelta(days=day_offset)
            for service_area, spec in SERVICE_DEFINITIONS.items():
                low, high = spec["daily_range"]
                encounter_count = random.randint(low, high)
                if is_hospital:
                    encounter_count += 1
                if is_central and service_area in {"Labour", "Newborn"}:
                    encounter_count += 1

                for local_idx in range(encounter_count):
                    person_id += 1
                    encounter_id += 1
                    visit_id += 1
                    encounter_dt = day_dt + timedelta(hours=random.randint(7, 16), minutes=random.randint(0, 59))
                    base_row = make_base_row(
                        template_columns,
                        facility_meta,
                        service_area,
                        encounter_dt,
                        person_id,
                        encounter_id,
                        visit_id,
                        local_idx + facility_idx * 100,
                    )
                    for concept_name, concept_type, values, numeric_range in spec["concepts"]:
                        rule = concept_rule(service_area, concept_name)
                        include_probability = float(rule.get("include_probability", 1.0))
                        if random.random() > include_probability:
                            continue
                        row = base_row.copy()
                        coded_value, text_value, numeric_value = concept_value(concept_type, values, numeric_range)
                        weights = rule.get("weights")
                        if weights and values and concept_type in {"coded", "value"} and len(weights) == len(values):
                            chosen = random.choices(values, weights=weights, k=1)[0]
                            if concept_type == "coded":
                                coded_value, text_value, numeric_value = chosen, None, None
                            else:
                                coded_value, text_value, numeric_value = None, chosen, None
                        row["concept_name"] = concept_name
                        row["obs_value_coded"] = coded_value
                        row["Value"] = text_value
                        row["ValueN"] = numeric_value
                        if service_area == "Newborn":
                            row["Age"] = 0.0
                            row["AgeDays"] = random.randint(0, 28)
                            row["Age_Group"] = "Under 5"
                        month_key = row["month_key"]
                        rows_by_month.setdefault(month_key, []).append(row)
                        row_count += 1
    return rows_by_month, row_count


def recreate_output_dir(output_dir: str) -> None:
    if os.path.isdir(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)


def write_demo_rows(template_columns: list[str], rows_by_month: dict[str, list[dict]], output_dir: str) -> None:
    for month_key, month_rows in rows_by_month.items():
        month_df = pd.DataFrame.from_records(month_rows, columns=template_columns)
        for col in ["Date", "obs_datetime", "value_datetime", "birthdate", "date_started", "date_stopped"]:
            if col in month_df.columns:
                month_df[col] = pd.to_datetime(month_df[col], errors="coerce")
        month_file = os.path.join(output_dir, f"data_{month_key}.parquet")
        month_df.to_parquet(month_file, index=False)


def write_timestamp() -> None:
    try:
        os.makedirs("data", exist_ok=True)
        pd.DataFrame({"saving_time": [datetime.now().strftime("%d/%m/%Y, %H:%M:%S")]}).to_csv(
            os.path.join("data", "TimeStamp.csv"), index=False
        )
    except PermissionError:
        pass


def main() -> None:
    random.seed(SEED)
    args = parse_args()
    source_files = load_source_files(args.source)
    template_columns = load_template_columns(source_files)
    person_max, encounter_max, visit_max = get_max_ids(source_files)
    rows_by_month, row_count = build_demo_rows(
        template_columns,
        person_max,
        encounter_max,
        visit_max,
        args.start_date,
        args.end_date,
    )
    recreate_output_dir(args.output)
    write_demo_rows(template_columns, rows_by_month, args.output)
    write_timestamp()
    print(f"Demo dataset written to {args.output}")
    print(f"Facilities: {len(DEMO_FACILITIES)}")
    print(f"Rows added: {row_count}")


if __name__ == "__main__":
    main()
