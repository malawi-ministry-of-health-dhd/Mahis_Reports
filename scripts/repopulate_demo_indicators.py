from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).parent.absolute()
BASE_DIR = SCRIPT_DIR.parent
TARGET_FILE = BASE_DIR / "demo_parquet" / "data_202606.parquet"


@dataclass
class Templates:
    anc: pd.Series
    labour: pd.Series
    pnc: pd.Series
    newborn: pd.Series


def _load_templates(df: pd.DataFrame) -> Templates:
    service = df["Service_Area"].fillna("").astype(str).str.upper()
    return Templates(
        anc=df.loc[service.str.contains("ANC", na=False)].iloc[0].copy(),
        labour=df.loc[service.str.contains("LABOUR", na=False)].iloc[0].copy(),
        pnc=df.loc[service.str.contains("PNC|POSTNATAL", na=False)].iloc[0].copy(),
        newborn=df.loc[service.str.contains("NEONATAL|NEWBORN", na=False)].iloc[0].copy(),
    )


def _new_row(template: pd.Series, *, person_id: int, encounter_id: int, date: str,
             concept: str | None = None, obs: str | None = None, value: str | None = None,
             value_n: float | None = None) -> dict:
    row = template.to_dict()
    row["person_id"] = person_id
    row["person_id_key"] = str(person_id)
    row["encounter_id"] = encounter_id
    row["Date"] = pd.Timestamp(date)
    row["months"] = pd.Timestamp(date).strftime("%Y-%m")
    row["value_datetime"] = ""
    row["count"] = 1
    row["count_set"] = 1
    row["sum"] = 1
    if concept is not None:
        row["concept_name"] = concept
    if obs is not None:
        row["obs_value_coded"] = obs
    if value is not None:
        row["Value"] = value
    if value_n is not None:
        row["ValueN"] = value_n
    elif concept is not None and concept not in {"Systolic blood pressure", "Diastolic blood pressure", "Temperature", "Birth weight"}:
        row["ValueN"] = None
    return row


def main() -> None:
    df = pd.read_parquet(TARGET_FILE)
    templates = _load_templates(df)

    next_person = int(pd.to_numeric(df["person_id"], errors="coerce").max()) + 1000
    next_encounter = int(pd.to_numeric(df["encounter_id"], errors="coerce").max()) + 1000
    rows: list[dict] = []

    def alloc_person() -> int:
        nonlocal next_person
        pid = next_person
        next_person += 1
        return pid

    def alloc_enc() -> int:
        nonlocal next_encounter
        eid = next_encounter
        next_encounter += 1
        return eid

    # ANC: at least 4 contacts
    anc_person = alloc_person()
    for d in ["2026-06-02", "2026-06-06", "2026-06-10", "2026-06-14"]:
        rows.append(_new_row(templates.anc, person_id=anc_person, encounter_id=alloc_enc(), date=d))

    # ANC: obstetric complication
    anc_comp = alloc_person()
    rows.append(_new_row(templates.anc, person_id=anc_comp, encounter_id=alloc_enc(), date="2026-06-12",
                         concept="Obstetric complications", obs="Sepsis", value="Sepsis"))

    # Labour: partograph
    labour_partograph = alloc_person()
    rows.append(_new_row(templates.labour, person_id=labour_partograph, encounter_id=alloc_enc(), date="2026-06-05",
                         concept="Was a partograph used", obs="Yes", value="Yes"))

    # Labour: antibiotic prophylaxis
    labour_abx = alloc_person()
    rows.append(_new_row(templates.labour, person_id=labour_abx, encounter_id=alloc_enc(), date="2026-06-06",
                         concept="Prophylactic azithromycin given", obs="Yes", value="Yes"))

    # Labour: uterotonic after birth
    labour_uterotonic = alloc_person()
    rows.append(_new_row(templates.labour, person_id=labour_uterotonic, encounter_id=alloc_enc(), date="2026-06-07",
                         concept="Oxytocin 10 iu given", obs="Yes", value="Yes"))

    # Labour: preterm labour + ACs
    labour_acs = alloc_person()
    rows.append(_new_row(templates.labour, person_id=labour_acs, encounter_id=alloc_enc(), date="2026-06-08",
                         concept="Obstetric complications", obs="preterm labour", value="preterm labour"))
    rows.append(_new_row(templates.labour, person_id=labour_acs, encounter_id=alloc_enc(), date="2026-06-08",
                         concept="Antenatal corticosteroids given", obs="Yes", value="Yes"))

    # Labour: PPH bundle
    labour_pph = alloc_person()
    rows.append(_new_row(templates.labour, person_id=labour_pph, encounter_id=alloc_enc(), date="2026-06-10",
                         concept="PPH", obs="Yes", value="Yes"))
    rows.append(_new_row(templates.labour, person_id=labour_pph, encounter_id=alloc_enc(), date="2026-06-10",
                         concept="Oxytocin 10 iu given", obs="Yes", value="Yes"))
    rows.append(_new_row(templates.labour, person_id=labour_pph, encounter_id=alloc_enc(), date="2026-06-10",
                         concept="1g Tranexamic Acid IV slow push over 10 minutes", obs="Yes", value="Yes"))

    # Labour: eclampsia + magnesium sulphate
    labour_mag = alloc_person()
    rows.append(_new_row(templates.labour, person_id=labour_mag, encounter_id=alloc_enc(), date="2026-06-11",
                         concept="Obstetric complications", obs="eclampsia", value="eclampsia"))
    rows.append(_new_row(templates.labour, person_id=labour_mag, encounter_id=alloc_enc(), date="2026-06-11",
                         concept="Magnesium sulphate given", obs="Yes", value="Yes"))

    # PNC: breastfeeding, BP, temperature, vitamin K at birth
    pnc_person = alloc_person()
    rows.append(_new_row(templates.pnc, person_id=pnc_person, encounter_id=alloc_enc(), date="2026-06-12"))
    rows.append(_new_row(templates.pnc, person_id=pnc_person, encounter_id=alloc_enc(), date="2026-06-12",
                         concept="Breast feeding", obs="Yes", value="Yes"))
    rows.append(_new_row(templates.pnc, person_id=pnc_person, encounter_id=alloc_enc(), date="2026-06-12",
                         concept="Systolic blood pressure", obs="", value="120", value_n=120))
    rows.append(_new_row(templates.pnc, person_id=pnc_person, encounter_id=alloc_enc(), date="2026-06-12",
                         concept="Diastolic blood pressure", obs="", value="80", value_n=80))
    rows.append(_new_row(templates.pnc, person_id=pnc_person, encounter_id=alloc_enc(), date="2026-06-12",
                         concept="Temperature", obs="", value="36.8", value_n=36.8))
    rows.append(_new_row(templates.labour, person_id=pnc_person, encounter_id=alloc_enc(), date="2026-06-12",
                         concept="Vitamin K given", obs="Yes", value="Yes"))

    # PNC: mother and newborn complications
    pnc_comp = alloc_person()
    rows.append(_new_row(templates.pnc, person_id=pnc_comp, encounter_id=alloc_enc(), date="2026-06-13",
                         concept="Postnatal complications", obs="Sepsis", value="Sepsis"))
    rows.append(_new_row(templates.pnc, person_id=pnc_comp, encounter_id=alloc_enc(), date="2026-06-13",
                         concept="Newborn baby complications", obs="Jaundice", value="Jaundice"))

    # Newborn: resuscitation eligibility + intervention
    nb_resus = alloc_person()
    rows.append(_new_row(templates.newborn, person_id=nb_resus, encounter_id=alloc_enc(), date="2026-06-13",
                         concept="Eligible for neonatal resuscitation", obs="Yes", value="Yes"))
    rows.append(_new_row(templates.newborn, person_id=nb_resus, encounter_id=alloc_enc(), date="2026-06-13",
                         concept="Neonatal resuscitation provided", obs="Bag and mask", value="Bag and mask"))
    rows.append(_new_row(templates.newborn, person_id=nb_resus, encounter_id=alloc_enc(), date="2026-06-13",
                         concept="Birth asphyxia suspected", obs="Yes", value="Yes"))

    # Newborn: sepsis + antibiotics
    nb_sepsis = alloc_person()
    rows.append(_new_row(templates.newborn, person_id=nb_sepsis, encounter_id=alloc_enc(), date="2026-06-14",
                         concept="Neonatal Sepsis - Early Onset", obs="Yes", value="Yes"))
    rows.append(_new_row(templates.newborn, person_id=nb_sepsis, encounter_id=alloc_enc(), date="2026-06-14",
                         concept="Parenteral antibiotics given", obs="Yes", value="Yes"))

    # Newborn: jaundice + bilirubin + phototherapy
    nb_jaundice = alloc_person()
    rows.append(_new_row(templates.newborn, person_id=nb_jaundice, encounter_id=alloc_enc(), date="2026-06-15",
                         concept="Clinical jaundice", obs="Yes", value="Yes"))
    rows.append(_new_row(templates.newborn, person_id=nb_jaundice, encounter_id=alloc_enc(), date="2026-06-15",
                         concept="Bilirubin level", obs="Measured", value="Measured"))
    rows.append(_new_row(templates.newborn, person_id=nb_jaundice, encounter_id=alloc_enc(), date="2026-06-15",
                         concept="Phototherapy given", obs="Yes", value="Yes"))
    rows.append(_new_row(templates.newborn, person_id=nb_jaundice, encounter_id=alloc_enc(), date="2026-06-15",
                         concept="Status of baby", obs="Alive", value="Alive"))

    # Newborn: pulse oximeter / oxygen saturation
    nb_ox = alloc_person()
    rows.append(_new_row(templates.newborn, person_id=nb_ox, encounter_id=alloc_enc(), date="2026-06-16",
                         concept="Pulse oximeter used at admission", obs="Yes", value="Yes"))
    rows.append(_new_row(templates.newborn, person_id=nb_ox, encounter_id=alloc_enc(), date="2026-06-16",
                         concept="Status of baby", obs="Alive", value="Alive"))

    # Newborn: neonatal death recorded inside current visible month window
    nb_death = alloc_person()
    rows.append(_new_row(templates.newborn, person_id=nb_death, encounter_id=alloc_enc(), date="2026-06-16",
                         concept="Status of baby", obs="Death", value="Death"))

    # Newborn denominator + breastfeeding within 1 hour
    nb_bf = alloc_person()
    rows.append(_new_row(templates.newborn, person_id=nb_bf, encounter_id=alloc_enc(), date="2026-06-16"))
    rows.append(_new_row(templates.labour, person_id=nb_bf, encounter_id=alloc_enc(), date="2026-06-16",
                         concept="Breast feeding", obs="Yes", value="Yes"))
    rows.append(_new_row(templates.newborn, person_id=nb_bf, encounter_id=alloc_enc(), date="2026-06-16",
                         concept="Status of baby", obs="Alive", value="Alive"))

    out = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    out.to_parquet(TARGET_FILE, index=False)
    print(f"Added {len(rows)} synthetic rows to {TARGET_FILE}")


if __name__ == "__main__":
    main()
