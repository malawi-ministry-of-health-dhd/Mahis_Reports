"""
Update validated_dashboard.json — replace priority_indicators for the MCH entry
with the full MNID indicator set, now using confirmed concept names from live data.
"""
import json, os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with open('data/visualizations/validated_dashboard.json') as f:
    dash_data = json.load(f)

mch = next(d for d in dash_data if 'Maternal' in d['report_name'])

mch['visualization_types']['priority_indicators'] = [

    # ══ ANC ══════════════════════════════════════════════════════════════════

    {
        "id": "mnid_anc_001", "label": "ANC screened for anaemia",
        "category": "ANC", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Anemia screening",
            "variable2": "obs_value_coded", "value2": "Screened"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Anemia screening"
        }
    },
    {
        "id": "mnid_anc_002", "label": "ANC screened for infection",
        "category": "ANC", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Infection screening",
            "variable2": "obs_value_coded", "value2": "Screened"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Infection screening"
        }
    },
    {
        "id": "mnid_anc_003", "label": "ANC screened for high blood pressure",
        "category": "ANC", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "High blood pressure screening",
            "variable2": "obs_value_coded", "value2": "Screened"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "High blood pressure screening"
        }
    },
    {
        "id": "mnid_anc_004", "label": "HIV-tested + screened for anaemia + high BP",
        "category": "ANC", "target": 80, "status": "awaiting_baseline",
        "note": "Composite: requires same person to have HIV test AND anaemia screening AND BP screening in same encounter. Needs custom cross-concept logic."
    },
    {
        "id": "mnid_anc_005", "label": "POCUS with gestational age recorded",
        "category": "ANC", "target": 50, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "POCUS completed",
            "variable2": "obs_value_coded", "value2": "Yes"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "POCUS completed"
        }
    },
    {
        "id": "mnid_anc_006", "label": "ANC 2+ tetanus doses",
        "category": "ANC", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Number of tetanus doses",
            "variable2": "Value",
            "value2": ["two doses", "three doses", "four doses"]
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Encounter", "value1": "ANC VISIT"
        }
    },

    # ══ Labour & Delivery ════════════════════════════════════════════════════

    {
        "id": "mnid_lab_001", "label": "Quality intrapartum care per guidelines",
        "category": "Labour", "target": 80, "status": "awaiting_baseline",
        "note": "Composite: PPH, Sepsis, PET/ET, Obstructed labour all managed per protocol. Requires custom composite logic across multiple obs."
    },
    {
        "id": "mnid_lab_002", "label": "Digital intrapartum monitoring",
        "category": "Labour", "target": 70, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Digital intrapartum monitoring",
            "variable2": "obs_value_coded", "value2": "Used"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Digital intrapartum monitoring"
        }
    },
    {
        "id": "mnid_lab_003", "label": "Antenatal corticosteroids (pre-term labour)",
        "category": "Labour", "target": 70, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Antenatal corticosteroids given",
            "variable2": "obs_value_coded", "value2": "Yes"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Antenatal corticosteroids given",
            "variable2": "obs_value_coded", "value2": ["Yes", "No"]
        }
    },
    {
        "id": "mnid_lab_004", "label": "Prophylactic azithromycin in labour",
        "category": "Labour", "target": 50, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Prophylactic azithromycin given",
            "variable2": "obs_value_coded", "value2": "Yes"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Prophylactic azithromycin given"
        }
    },
    {
        "id": "mnid_lab_005", "label": "PPH early detection + WHO treatment bundle",
        "category": "Labour", "target": 70, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "PPH treatment bundle",
            "variable2": "obs_value_coded", "value2": "Completed"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "PPH treatment bundle",
            "variable2": "obs_value_coded", "value2": ["Completed", "Partial"]
        }
    },
    {
        "id": "mnid_lab_006", "label": "Facility deliveries",
        "category": "Labour", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Place of delivery",
            "variable2": "obs_value_coded", "value2": ["This facility", "this facility"]
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Place of delivery"
        }
    },
    {
        "id": "mnid_lab_007", "label": "Skilled delivery attendance",
        "category": "Labour", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Staff conducting delivery"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Mode of delivery"
        }
    },

    # ══ Newborn ══════════════════════════════════════════════════════════════

    {
        "id": "mnid_nb_001", "label": "Neonatal resuscitation (eligible babies)",
        "category": "Newborn", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Neonatal resuscitation provided",
            "variable2": "obs_value_coded",
            "value2": ["Yes", "Stimulation only", "Bag and mask"]
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Eligible for neonatal resuscitation",
            "variable2": "obs_value_coded", "value2": "Yes"
        }
    },
    {
        "id": "mnid_nb_002", "label": "iKMC (preterm / low birth-weight babies)",
        "category": "Newborn", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "iKMC initiated",
            "variable2": "obs_value_coded", "value2": "Yes"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "iKMC initiated",
            "variable2": "obs_value_coded", "value2": ["Yes", "No"]
        }
    },
    {
        "id": "mnid_nb_003", "label": "Prophylactic CPAP (1000–1499g babies)",
        "category": "Newborn", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "CPAP support",
            "variable2": "obs_value_coded", "value2": ["Bubble CPAP", "Nasal oxygen"]
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "CPAP support"
        }
    },
    {
        "id": "mnid_nb_004", "label": "CPAP for eligible babies (1500–1999g)",
        "category": "Newborn", "target": 80, "status": "awaiting_baseline",
        "note": "Requires birth weight field to separate 1500–1999g cohort from 1000–1499g. Birth weight not yet captured as a distinct filterable concept."
    },
    {
        "id": "mnid_nb_005", "label": "Phototherapy for jaundice",
        "category": "Newborn", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Phototherapy given",
            "variable2": "obs_value_coded", "value2": "Yes"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Phototherapy given"
        }
    },
    {
        "id": "mnid_nb_006", "label": "Parenteral antibiotics for sepsis",
        "category": "Newborn", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Parenteral antibiotics given",
            "variable2": "obs_value_coded", "value2": "Yes"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Parenteral antibiotics given"
        }
    },
    {
        "id": "mnid_nb_007", "label": "Not hypothermic on NNU admission",
        "category": "Newborn", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Thermal status on admission",
            "variable2": "obs_value_coded", "value2": "Not hypothermic"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Thermal status on admission"
        }
    },
    {
        "id": "mnid_nb_008", "label": "Not hypothermic at any time (NNU stay)",
        "category": "Newborn", "target": 80, "status": "awaiting_baseline",
        "note": "Longitudinal: requires all temperature readings within NNU stay to be in normal range. Needs time-series logic not yet supported."
    },

    # ══ PNC ══════════════════════════════════════════════════════════════════

    {
        "id": "mnid_pnc_001", "label": "PNC mothers within 48 hours",
        "category": "PNC", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Postnatal check period",
            "variable2": "obs_value_coded", "value2": "Up to 48 hrs or before discharge"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Postnatal check period"
        }
    },
    {
        "id": "mnid_pnc_002", "label": "BCG vaccination coverage",
        "category": "PNC", "target": 90, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name",
            "value1": ["Type of immunization the baby received", "Immunisation given"],
            "variable2": "obs_value_coded", "value2": ["BCG", "bcg"]
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name",
            "value1": ["Type of immunization the baby received", "Immunisation given"]
        }
    },
    {
        "id": "mnid_pnc_003", "label": "Exclusive breastfeeding",
        "category": "PNC", "target": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Breast feeding",
            "variable2": "obs_value_coded", "value2": ["Exclusive", "exclusive breastfeeding"]
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Breast feeding"
        }
    },
]

# ── Workforce / competency indicators (separate key for the workforce section)
mch['visualization_types']['workforce_indicators'] = [
    {
        "id": "mnid_wf_001", "label": "EmONC competency assessed",
        "target_count": 500, "target_pct": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "EmONC competency assessed",
            "variable2": "obs_value_coded", "value2": "Assessed"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "EmONC competency assessed"
        }
    },
    {
        "id": "mnid_wf_002", "label": "SSNC competency assessed",
        "target_count": 200, "target_pct": 80, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "SSNC competency assessed",
            "variable2": "obs_value_coded", "value2": "Assessed"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "SSNC competency assessed"
        }
    },
]

# ── Supply chain / equipment indicators
mch['visualization_types']['supply_indicators'] = [
    {
        "id": "mnid_sc_001", "label": "Essential medicine availability",
        "status": "tracked", "target_value": "All available",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Essential medicine availability",
            "variable2": "obs_value_coded", "value2": "All available"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Essential medicine availability"
        }
    },
    {
        "id": "mnid_sc_002", "label": "CPAP equipment available",
        "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "CPAP equipment status",
            "variable2": "obs_value_coded", "value2": "Available"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "CPAP equipment status"
        }
    },
    {
        "id": "mnid_sc_003", "label": "Phototherapy unit available",
        "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Phototherapy unit status",
            "variable2": "obs_value_coded", "value2": "Available"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Phototherapy unit status"
        }
    },
    {
        "id": "mnid_sc_004", "label": "Neonatal resuscitation equipment available",
        "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Newborn resuscitation equipment status",
            "variable2": "obs_value_coded", "value2": "Available"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Newborn resuscitation equipment status"
        }
    },
]

# ── Data quality indicators
mch['visualization_types']['data_quality_indicators'] = [
    {
        "id": "mnid_dq_001", "label": "Record completeness",
        "target_pct": 95, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Record completeness",
            "variable2": "obs_value_coded", "value2": "Complete"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Record completeness"
        }
    },
    {
        "id": "mnid_dq_002", "label": "Data entered within 7 days",
        "target_pct": 90, "status": "tracked",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Data entered within 7 days",
            "variable2": "obs_value_coded", "value2": "Yes"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Data entered within 7 days"
        }
    },
]

with open('data/visualizations/validated_dashboard.json', 'w') as f:
    json.dump(dash_data, f, indent=2)

inds = mch['visualization_types']['priority_indicators']
tracked  = [i for i in inds if i['status'] == 'tracked']
awaiting = [i for i in inds if i['status'] == 'awaiting_baseline']
print(f"priority_indicators: {len(inds)} total | {len(tracked)} tracked | {len(awaiting)} awaiting")
print(f"workforce_indicators: {len(mch['visualization_types']['workforce_indicators'])}")
print(f"supply_indicators:    {len(mch['visualization_types']['supply_indicators'])}")
print(f"data_quality:         {len(mch['visualization_types']['data_quality_indicators'])}")
