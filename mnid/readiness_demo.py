"""Demo readiness dataset generation for executive MNID dashboards."""
from __future__ import annotations

import hashlib

import pandas as pd


def _stable_int(seed: str, low: int, high: int) -> int:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16)
    return low + (value % (high - low + 1))


def _default_district_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(
            [
                {"Facility_CODE": "3001", "Facility": "Queen Elizabeth Central Hospital", "District": "Blantyre"},
                {"Facility_CODE": "3008", "Facility": "Mzuzu District Hospital", "District": "Mzimba"},
                {"Facility_CODE": "3006", "Facility": "Dedza District Hospital", "District": "Dedza"},
                {"Facility_CODE": "3004", "Facility": "Ntcheu District Hospital", "District": "Ntcheu"},
                {"Facility_CODE": "3014", "Facility": "Mangochi District Hospital", "District": "Mangochi"},
                {"Facility_CODE": "3013", "Facility": "Salima District Hospital", "District": "Salima"},
            ]
        )
    cols = [col for col in ["Facility_CODE", "Facility", "District"] if col in df.columns]
    if len(cols) < 3:
        return _default_district_rows(pd.DataFrame())
    return df[cols].dropna().drop_duplicates()


def generate_demo_readiness_data(df: pd.DataFrame) -> dict:
    facility_rows = _default_district_rows(df)
    if facility_rows.empty:
        facility_rows = _default_district_rows(pd.DataFrame())

    readiness_rows = []
    for _, row in facility_rows.iterrows():
        code = str(row["Facility_CODE"])
        district = str(row["District"])
        facility = str(row["Facility"])
        midwives = _stable_int(f"{code}:midwives", 42, 88)
        clinicians = _stable_int(f"{code}:clinicians", 36, 81)
        vacancy = _stable_int(f"{code}:vacancy", 8, 39)
        staffing_score = max(int((midwives + clinicians) / 2 - vacancy * 0.35), 24)

        oxytocin = _stable_int(f"{code}:oxytocin", 72, 96)
        magnesium = _stable_int(f"{code}:magnesium", 48, 82)
        antibiotics = _stable_int(f"{code}:antibiotics", 57, 89)
        essential = _stable_int(f"{code}:essential", 34, 78)

        warmers_available = _stable_int(f"{code}:warmers:avail", 58, 94)
        warmers_functional = max(warmers_available - _stable_int(f"{code}:warmers:gap", 6, 24), 12)
        beds_available = _stable_int(f"{code}:beds:avail", 64, 96)
        beds_functional = max(beds_available - _stable_int(f"{code}:beds:gap", 3, 16), 18)
        resus_available = _stable_int(f"{code}:resus:avail", 41, 86)
        resus_functional = max(resus_available - _stable_int(f"{code}:resus:gap", 6, 18), 10)
        cpap_available = _stable_int(f"{code}:cpap:avail", 18, 58)
        cpap_functional = max(cpap_available - _stable_int(f"{code}:cpap:gap", 4, 14), 4)

        assessed = _stable_int(f"{code}:assessed", 1, 1)
        meeting = 1 if staffing_score >= 65 and essential >= 55 and resus_functional >= 35 else 0

        readiness_rows.append(
            {
                "Facility_CODE": code,
                "Facility": facility,
                "District": district,
                "midwives": midwives,
                "clinicians": clinicians,
                "vacancy_rate": vacancy,
                "staffing_score": staffing_score,
                "oxytocin": oxytocin,
                "magnesium": magnesium,
                "antibiotics": antibiotics,
                "essential_medicines": essential,
                "warmers_available": warmers_available,
                "warmers_functional": warmers_functional,
                "beds_available": beds_available,
                "beds_functional": beds_functional,
                "resus_available": resus_available,
                "resus_functional": resus_functional,
                "cpap_available": cpap_available,
                "cpap_functional": cpap_functional,
                "assessed": assessed,
                "meeting": meeting,
            }
        )

    readiness_df = pd.DataFrame(readiness_rows)
    readiness_df["need_support"] = 1 - readiness_df["meeting"]
    readiness_df["national_score"] = (
        readiness_df["staffing_score"] * 0.35
        + readiness_df["essential_medicines"] * 0.25
        + readiness_df["resus_functional"] * 0.20
        + readiness_df["oxytocin"] * 0.20
    ).round(1)

    district_df = (
        readiness_df.groupby("District", as_index=False)
        .agg(
            midwives=("midwives", "mean"),
            clinicians=("clinicians", "mean"),
            vacancy_rate=("vacancy_rate", "mean"),
            staffing_score=("staffing_score", "mean"),
            oxytocin=("oxytocin", "mean"),
            magnesium=("magnesium", "mean"),
            antibiotics=("antibiotics", "mean"),
            essential_medicines=("essential_medicines", "mean"),
            warmers_available=("warmers_available", "mean"),
            warmers_functional=("warmers_functional", "mean"),
            beds_available=("beds_available", "mean"),
            beds_functional=("beds_functional", "mean"),
            resus_available=("resus_available", "mean"),
            resus_functional=("resus_functional", "mean"),
            cpap_available=("cpap_available", "mean"),
            cpap_functional=("cpap_functional", "mean"),
            assessed=("assessed", "sum"),
            meeting=("meeting", "sum"),
            need_support=("need_support", "sum"),
            national_score=("national_score", "mean"),
        )
        .sort_values("national_score", ascending=False)
        .reset_index(drop=True)
    )

    month_labels = ["Jan 26", "Feb 26", "Mar 26", "Apr 26", "May 26", "Jun 26"]
    assessment_trend = []
    for index, month in enumerate(month_labels):
        assessed = int(readiness_df["assessed"].sum() * (0.92 + index * 0.015))
        meeting = int(assessed * (0.38 + index * 0.01))
        assessment_trend.append(
            {
                "month": month,
                "assessed": assessed,
                "meeting": meeting,
                "support": max(assessed - meeting, 0),
            }
        )

    procurement = [
        {
            "title": "Oxytocin batch #OXY-2025-11",
            "detail": "12,000 vials",
            "note": "Distributed across 186 facilities · Southern & Central Region",
            "status": "Delivered",
            "eta": "2 Jun 2026",
            "tone": "green",
        },
        {
            "title": "CPAP machines",
            "detail": "48 units",
            "note": "En route to Northern Region facilities",
            "status": "In transit",
            "eta": "ETA 14 Jun",
            "tone": "blue",
        },
        {
            "title": "Magnesium sulphate",
            "detail": "8,400 ampoules",
            "note": "Procurement order placed · awaiting dispatch from central store",
            "status": "Pending",
            "eta": "Est. 28 Jun",
            "tone": "amber",
        },
        {
            "title": "Neonatal resuscitation kits",
            "detail": "220 units",
            "note": "Budget approved · vendor not yet confirmed",
            "status": "Pending",
            "eta": "Est. Jul 2026",
            "tone": "amber",
        },
    ]

    return {
        "facility_readiness": readiness_df,
        "district_readiness": district_df,
        "assessment_trend": assessment_trend,
        "procurement": procurement,
    }
