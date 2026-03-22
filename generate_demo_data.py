from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


FACILITIES = [
    {"code": "LL040033", "name": "Lilongwe Central", "district": "Lilongwe", "ta": "Chilinde", "village": "Area 25"},
    {"code": "BT020011", "name": "Bwaila District", "district": "Lilongwe", "ta": "Kalumba", "village": "Area 18"},
    {"code": "MZ120004", "name": "Mzuzu Urban", "district": "Mzuzu", "ta": "Mchengautuwa", "village": "Luwinga"},
    {"code": "BL050022", "name": "Blantyre South", "district": "Blantyre", "ta": "Kapeni", "village": "Ndirande"},
]

FIRST_NAMES = ["Mercy", "Thokozani", "James", "Mary", "Peter", "Agnes", "Grace", "John", "Chikondi", "Ruth"]
LAST_NAMES = ["Banda", "Phiri", "Mvula", "Zulu", "Mhango", "Mbewe", "Tembo", "Jere", "Gondwe", "Kaunda"]
GENDERS = ["Male", "Female"]


def build_demo_data() -> pd.DataFrame:
    """Seed a broad synthetic dataset that matches the dashboard filter vocabulary."""
    random.seed(42)
    today = datetime.now().date()
    start_date = today - timedelta(days=180)

    rows: list[dict] = []
    encounter_id = 100000
    person_id = 1

    def next_encounter_id() -> int:
        nonlocal encounter_id
        encounter_id += 1
        return encounter_id

    def add_row(
        *,
        person: int,
        date_value,
        program: str,
        facility: dict,
        home_facility: dict,
        gender: str,
        age: int,
        visit_days: int,
        new_revisit: str,
        encounter: str,
        concept_name: str = "",
        obs_value_coded: str = "",
        value: str = "",
        value_numeric: float | int = 0,
        drug_name: str = "",
        order_name: str = "",
        value_name: str = "",
    ) -> None:
        rows.append(
            {
                "person_id": person,
                "encounter_id": next_encounter_id(),
                "given_name": random.choice(FIRST_NAMES),
                "family_name": random.choice(LAST_NAMES),
                "Gender": gender,
                "Age": age,
                "Age_Group": "Under 5" if age < 5 else "Over 5",
                "Date": pd.to_datetime(date_value),
                "Program": program,
                "Facility": facility["name"],
                "Facility_CODE": facility["code"],
                "User": f"demo-user-{facility['code'][-2:]}",
                "District": facility["district"],
                "Encounter": encounter,
                "Home_district": home_facility["district"],
                "TA": home_facility["ta"],
                "Village": home_facility["village"],
                "visit_days": visit_days,
                "obs_value_coded": obs_value_coded,
                "concept_name": concept_name,
                "Value": value,
                "ValueN": value_numeric,
                "DrugName": drug_name,
                "Value_name": value_name,
                "new_revisit": new_revisit,
                "Order_Name": order_name,
                "count": None,
                "count_set": None,
                "sum": None,
            }
        )

    def random_facility():
        return random.choice(FACILITIES), random.choice(FACILITIES)

    def generate_opd_records(start_person: int, count: int) -> int:
        diagnoses = ["Malaria", "Pneumonia", "Diarrhea", "Upper Respiratory Infection", "Skin Infection"]
        complaints = ["Fever", "Cough", "Body pains", "Diarrhea", "Headache"]
        malaria_drugs = [
            "Lumefantrine + Arthemether 1 x 6",
            "Lumefantrine + Arthemether 2 x 6",
            "ASAQ 100mg/270mg (3 tablets)",
            "ASAQ 50mg/135mg (3 tablets)",
        ]
        general_drugs = ["Paracetamol", "Amoxicillin", "ORS", "Cotrimoxazole"]
        lab_tests = ["Malaria RDT", "HIV test", "Full Blood Count", "Urinalysis"]
        outcomes = ["Discharged home", "Admitted", "Death"]

        person = start_person
        for _ in range(count):
            facility, home_facility = random_facility()
            gender = random.choice(GENDERS)
            age = random.randint(1, 70)
            visit_count = random.randint(1, 4)
            offsets = sorted(random.sample(range(0, 160), visit_count))
            diagnosis = random.choice(diagnoses)

            for index, offset in enumerate(offsets, start=1):
                visit_date = start_date + timedelta(days=offset)
                revisit = "New" if index == 1 else "Revisit"
                add_row(person=person, date_value=visit_date, program="OPD Program", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="VITALS", concept_name="Systolic blood pressure", value_numeric=random.randint(95, 165))
                add_row(person=person, date_value=visit_date, program="OPD Program", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="VITALS", concept_name="Diastolic blood pressure", value_numeric=random.randint(60, 105))
                add_row(person=person, date_value=visit_date, program="OPD Program", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="PRESENTING COMPLAINTS", concept_name="Presenting complaint", obs_value_coded=random.choice(complaints))
                add_row(person=person, date_value=visit_date, program="OPD Program", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="DIAGNOSIS", concept_name="Primary diagnosis", obs_value_coded=diagnosis)
                add_row(person=person, date_value=visit_date, program="OPD Program", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LAB ORDERS", concept_name="Test type", obs_value_coded=random.choice(lab_tests))
                add_row(person=person, date_value=visit_date, program="OPD Program", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="DISPENSING", concept_name="Medications dispensed", drug_name=random.choice(malaria_drugs if diagnosis == "Malaria" else general_drugs))
                add_row(person=person, date_value=visit_date, program="OPD Program", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="PATIENT OUTCOME", concept_name=random.choice(outcomes), obs_value_coded=random.choice(outcomes))
            person += 1
        return person

    def generate_ncd_records(start_person: int, count: int) -> int:
        diagnoses = ["Type 1 diabetes", "Type 2 diabetes", "Hypertension", "Asthma", "Heart Failure"]
        drugs = ["Amlodipine", "Metformin", "Hydrochlorothiazide", "Enalapril", "Salbutamol"]

        person = start_person
        for _ in range(count):
            facility, home_facility = random_facility()
            gender = random.choice(GENDERS)
            age = random.randint(18, 79)
            visit_count = random.randint(1, 5)
            offsets = sorted(random.sample(range(0, 180), visit_count))
            diagnosis = random.choice(diagnoses)

            for index, offset in enumerate(offsets, start=1):
                visit_date = start_date + timedelta(days=offset)
                revisit = "New" if index == 1 else "Revisit"
                add_row(person=person, date_value=visit_date, program="NCD PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="OUTPATIENT DIAGNOSIS", obs_value_coded=diagnosis)
                add_row(person=person, date_value=visit_date, program="NCD PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="DIAGNOSIS", obs_value_coded=diagnosis)
                add_row(person=person, date_value=visit_date, program="NCD PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="PAST MEDICAL HISTORY", concept_name="Does the patient drink alcohol?", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="NCD PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="PAST MEDICAL HISTORY", concept_name="Smoking history", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="NCD PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="DISPENSING", concept_name="Medications dispensed", drug_name=random.choice(drugs), value_numeric=random.randint(1, 60))
            person += 1
        return person

    def generate_immunisation_records(start_person: int, count: int) -> int:
        vaccines = ["BCG", "Penta 1", "Penta 3", "MR 1", "MR 2"]
        person = start_person
        for _ in range(count):
            facility, home_facility = random_facility()
            gender = random.choice(GENDERS)
            age = random.randint(0, 4)
            visit_count = random.randint(1, 3)
            offsets = sorted(random.sample(range(0, 150), visit_count))
            for index, offset in enumerate(offsets, start=1):
                visit_date = start_date + timedelta(days=offset)
                revisit = "New" if index == 1 else "Revisit"
                add_row(person=person, date_value=visit_date, program="IMMUNIZATION PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="TREATMENT", concept_name="Medications dispensed", value=random.choice(vaccines))
            person += 1
        return person

    def generate_hts_records(start_person: int, count: int) -> int:
        person = start_person
        for _ in range(count):
            facility, home_facility = random_facility()
            gender = random.choice(GENDERS)
            age = random.randint(12, 60)
            visit_count = random.randint(1, 2)
            offsets = sorted(random.sample(range(0, 140), visit_count))
            for index, offset in enumerate(offsets, start=1):
                visit_date = start_date + timedelta(days=offset)
                revisit = "New" if index == 1 else "Revisit"
                hiv_value = random.choice(["Reactive", "Non-reactive"])
                add_row(person=person, date_value=visit_date, program="HTS PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="HIV STATUS AT ENROLLMENT", concept_name="HIV status", obs_value_coded="Unknown" if hiv_value == "Non-reactive" else "New Positive", value=hiv_value)
                add_row(person=person, date_value=visit_date, program="HTS PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LAB ORDERS", concept_name="HIV test", obs_value_coded="HIV test")
                add_row(person=person, date_value=visit_date, program="HTS PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LAB RESULTS", concept_name="HIV test", value=hiv_value)
                if hiv_value == "Reactive":
                    add_row(person=person, date_value=visit_date, program="HTS PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="PATIENT OUTCOME", concept_name="ART referral", obs_value_coded="Yes")
            person += 1
        return person

    def generate_neonatal_records(start_person: int, count: int) -> int:
        outcomes = ["Discharged home (Well Baby)", "Referrer to main hospital", "Absconded", "Died", "Neonatal Death"]
        person = start_person
        for _ in range(count):
            facility, home_facility = random_facility()
            gender = random.choice(GENDERS)
            age = 0
            visit_count = random.randint(1, 3)
            offsets = sorted(random.sample(range(0, 120), visit_count))
            for index, offset in enumerate(offsets, start=1):
                visit_date = start_date + timedelta(days=offset)
                revisit = "New" if index == 1 else "Revisit"
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL ENROLMENT", concept_name="HIV status", obs_value_coded=random.choice(["Positive", "Negative", "Unknown"]))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL TRIAGE", obs_value_coded=random.choice(["Stable", "Urgent", "Critical"]))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL ADMISSION OUTCOMES", concept_name="Admission outcome", obs_value_coded=random.choice(outcomes))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="PATIENT OUTCOME", concept_name="Patient admission outcome", obs_value_coded=random.choice(outcomes))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL SYSTEMIC EXAMINATION", concept_name="Prematurity/Kangaroo", obs_value_coded=random.choice(["Prematurity", "KMC", "Normal weight"]))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL REVIEW OF SYSTEMS", concept_name="Vitamin K given", obs_value_coded=random.choice(["Yes", "No"]))
                # MNH-style neonatal intervention indicators.
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL RESUSCITATION", concept_name="Eligible for neonatal resuscitation", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL RESUSCITATION", concept_name="Neonatal resuscitation provided", obs_value_coded=random.choice(["Bag and mask", "Stimulation only", "Not required"]))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL SYSTEMIC EXAMINATION", concept_name="iKMC initiated", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL SYSTEMIC EXAMINATION", concept_name="CPAP support", obs_value_coded=random.choice(["Bubble CPAP", "Nasal oxygen", "None"]))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL REVIEW OF SYSTEMS", concept_name="Phototherapy given", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL REVIEW OF SYSTEMS", concept_name="Parenteral antibiotics given", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="NEONATAL PROGRAM", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="NEONATAL TRIAGE", concept_name="Thermal status on admission", obs_value_coded=random.choice(["Not hypothermic", "Mild hypothermia", "Moderate hypothermia"]))
            person += 1
        return person

    def generate_mch_records(start_person: int, count: int) -> int:
        person = start_person
        for _ in range(count):
            facility, home_facility = random_facility()
            gender = "Female"
            age = random.randint(16, 42)
            visit_count = random.randint(2, 5)
            offsets = sorted(random.sample(range(0, 170), visit_count))
            for index, offset in enumerate(offsets, start=1):
                visit_date = start_date + timedelta(days=offset)
                revisit = "New" if index == 1 else "Revisit"
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="ANC VISIT", concept_name="Number of tetanus doses", obs_value_coded=random.choice(["two doses", "three doses", "four doses"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="ANC VISIT", concept_name="Pregnancy planned", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="ANC VISIT", concept_name="Blood group rhesus factor", obs_value_coded=random.choice(["A+", "B+", "O+", "AB+"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="ANC VISIT", concept_name="HIV Test", obs_value_coded=random.choice(["Reactive", "Non-reactive"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="ANC VISIT", concept_name="Insecticide treated net given", obs_value_coded=random.choice(["Yes", "No"]))
                # ANC screening and diagnostic coverage indicators inspired by MNID requirements.
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="ANC VISIT", concept_name="Anemia screening", obs_value_coded=random.choice(["Screened", "Not screened"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="ANC VISIT", concept_name="Infection screening", obs_value_coded=random.choice(["Screened", "Not screened"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="ANC VISIT", concept_name="High blood pressure screening", obs_value_coded=random.choice(["Screened", "Not screened"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="ANC VISIT", concept_name="POCUS completed", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="ANC VISIT", concept_name="Gestational age recorded", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="Place of delivery", obs_value_coded=random.choice(["This facility", "this facility", "Referral facility"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="Mode of delivery", obs_value_coded=random.choice(["Caesarean section", "caesarean section", "Spontaneous vertex delivery"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="Staff conducting delivery", obs_value_coded=random.choice(["Nurse Midwife", "Clinical Officer", "Doctor"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="Obstetric complications", obs_value_coded=random.choice(["None", "Pre-eclampsia", "Hemorrhage"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="Newborn baby complications", obs_value_coded=random.choice(["Birth asphyxia", "Sepsis", "Low birth weight"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="Management given to newborn", obs_value_coded=random.choice(["Antibiotics", "Resuscitation", "KMC"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="Outcome of the delivery", obs_value_coded=random.choice(["Live birth", "Stillbirth", "Twin delivery"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="referral reasons", obs_value_coded=random.choice(["Bleeding", "Hypertension", "Foetal distress"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="Digital intrapartum monitoring", obs_value_coded=random.choice(["Used", "Not used"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="Antenatal corticosteroids given", obs_value_coded=random.choice(["Yes", "No", "Not eligible"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="Prophylactic azithromycin given", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="LABOUR AND DELIVERY", concept_name="PPH treatment bundle", obs_value_coded=random.choice(["Completed", "Partial", "Not required"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Postnatal check period", obs_value_coded=random.choice(["Up to 48 hrs or before discharge", "3-7 days", "8-42 days"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Status of the mother", obs_value_coded=random.choice(["Stable", "Referred", "Death"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Status of baby", obs_value_coded=random.choice(["Stable", "Referred", "Died"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Postnatal complications", obs_value_coded=random.choice(["Postpartum hemorrhage", "Sepsis", "Retained placenta"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Immunisation given", obs_value_coded=random.choice(["BCG", "Polio 0", "None"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Type of immunization the baby received", obs_value_coded=random.choice(["BCG", "OPV", "HepB"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Breast feeding", obs_value_coded=random.choice(["Exclusive", "Mixed", "Not breastfeeding"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Mother HIV Status", obs_value_coded=random.choice(["positive", "negative", "unknown"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Counselling on family planning", obs_value_coded=random.choice(["Yes", "No"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Postpartum family planning method", obs_value_coded=random.choice(["Depo", "Implant", "IUCD", "Natural methods"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Prematurity/Kangaroo", obs_value_coded=random.choice(["Prematurity", "KMC", "No KMC"]))
                add_row(person=person, date_value=visit_date, program="MATERNAL AND CHILD HEALTH", facility=facility, home_facility=home_facility, gender=gender, age=age, visit_days=visit_count, new_revisit=revisit, encounter="POSTNATAL CARE", concept_name="Vitamin K given", obs_value_coded=random.choice(["Yes", "No"]))
            person += 1
        return person

    person_id = generate_opd_records(person_id, 180)
    person_id = generate_ncd_records(person_id, 120)
    person_id = generate_immunisation_records(person_id, 100)
    person_id = generate_hts_records(person_id, 90)
    person_id = generate_neonatal_records(person_id, 90)
    person_id = generate_mch_records(person_id, 110)

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def main() -> None:
    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    dropdown_dir = data_dir / "dcc_dropdown_json"
    data_dir.mkdir(exist_ok=True)
    dropdown_dir.mkdir(parents=True, exist_ok=True)

    df = build_demo_data()
    parquet_path = data_dir / "latest_data_opd.parquet"
    df.to_parquet(parquet_path, index=False)

    dropdowns = {
        "programs": sorted(df["Program"].dropna().unique().tolist()),
        "encounters": sorted(df["Encounter"].dropna().unique().tolist()),
        "concepts": sorted(df["concept_name"].dropna().unique().tolist()),
    }
    with open(dropdown_dir / "dropdowns.json", "w", encoding="utf-8") as handle:
        json.dump(dropdowns, handle, indent=2)

    timestamp = pd.DataFrame({"saving_time": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]})
    timestamp.to_csv(data_dir / "TimeStamp.csv", index=False)

    summary = {
        "rows": int(len(df)),
        "facilities": df["Facility_CODE"].value_counts().to_dict(),
        "programs": df["Program"].value_counts().to_dict(),
        "date_min": str(df["Date"].min().date()),
        "date_max": str(df["Date"].max().date()),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
