"""
One-shot script: adds filter definitions for all "Tracked" indicators from
docs/indicator-status-overview.md that were previously marked awaiting_baseline
or missing entirely from the JSON dashboard files.
"""
import json
import os

NEW_DEFINITIONS = {
    # ── FIX: awaiting_baseline -> tracked (concepts confirmed in parquet) ─────

    "mnid_anc_001": {
        "action": "update",
        "status": "tracked",
        "note": "Tracked via Anemia screening concept (Yes/No) in ANC encounters.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "ANC",
            "variable2": "concept_name",  "value2": "Anemia screening",
            "variable3": "obs_value_coded", "value3": "Yes"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "ANC"
        }
    },

    "mnid_anc_004": {
        "action": "update",
        "label": "HIV-tested and screened (anaemia + high blood pressure)",
        "status": "tracked",
        "note": "Proxy: ANC clients with confirmed HIV test result. Full composite requires cross-row join not supported in current filter engine.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "ANC",
            "variable2": "concept_name",  "value2": "HIV Test",
            "variable3": "obs_value_coded", "value3": ["Negative", "Positive", "Reactive"]
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "ANC"
        }
    },

    "mnid_lab_003": {
        "action": "update",
        "label": "Eligible women with pre-term labour who received antenatal corticosteroids",
        "status": "tracked",
        "note": "Numerator: corticosteroids given=Yes in Labour. Denominator: corticosteroid eligibility assessed.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Labour",
            "variable2": "concept_name",  "value2": "Antenatal corticosteroids given",
            "variable3": "obs_value_coded", "value3": "Yes"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Labour",
            "variable2": "concept_name",  "value2": "Antenatal corticosteroids given"
        }
    },

    "mnid_nb_002": {
        "action": "update",
        "label": "Eligible preterm and low birth-weight babies who received iKMC",
        "status": "tracked",
        "note": "Proxy without weight-band filter (1000-1499g band not present in demo data). Tracks iKMC initiated among all Newborn encounters.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Newborn",
            "variable2": "concept_name",  "value2": "iKMC initiated",
            "variable3": "obs_value_coded", "value3": "Yes"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Newborn",
            "variable2": "concept_name",  "value2": "iKMC initiated"
        }
    },

    "mnid_nb_007": {
        "action": "update",
        "label": "Babies not hypothermic on admission to the neonatal unit",
        "status": "tracked",
        "target": 90,
        "note": "Direct from Thermal status on admission = Not hypothermic.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Newborn",
            "variable2": "concept_name",  "value2": "Thermal status on admission",
            "variable3": "obs_value_coded", "value3": "Not hypothermic"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Newborn",
            "variable2": "concept_name",  "value2": "Thermal status on admission"
        }
    },

    # ── ADD: new tracked indicators not yet in JSON ────────────────────────────

    "mnid_anc_extra_004": {
        "action": "add_to", "dashboard": "Maternal Health",
        "label": "Gestational age method recorded",
        "category": "ANC", "target": 80, "status": "tracked",
        "note": "GA recorded via LNMP, palpation, or ultrasound.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "ANC",
            "variable2": "concept_name",  "value2": "Gestational age recorded"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "ANC"
        }
    },

    "mnid_anc_extra_005": {
        "action": "add_to", "dashboard": "Maternal Health",
        "label": "ANC clients tested for HIV",
        "category": "ANC", "target": 95, "status": "tracked",
        "note": "ANC clients with any documented HIV test result (excludes Not done).",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "ANC",
            "variable2": "concept_name",  "value2": "HIV Test",
            "variable3": "obs_value_coded", "value3": ["Negative", "Positive", "Reactive"]
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "ANC"
        }
    },

    "mnid_lab_extra_004": {
        "action": "add_to", "dashboard": "Maternal Health",
        "label": "Delivery details recorded",
        "category": "Labour", "target": 95, "status": "tracked",
        "note": "Proxy: Labour encounters where mode of delivery was documented.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Labour",
            "variable2": "concept_name",  "value2": "Mode of delivery"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Labour"
        }
    },

    "mnid_lab_extra_005": {
        "action": "add_to", "dashboard": "Maternal Health",
        "label": "Births delivered by caesarean section",
        "category": "Labour", "target": 15, "status": "tracked",
        "note": "Rate: C-section proportion of deliveries with documented mode.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Labour",
            "variable2": "concept_name",  "value2": "Mode of delivery",
            "variable3": "obs_value_coded", "value3": "Caesarean section"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Labour",
            "variable2": "concept_name",  "value2": "Mode of delivery"
        }
    },

    "mnid_pnc_extra_001": {
        "action": "add_to", "dashboard": "Maternal Health",
        "label": "PNC visit documented",
        "category": "PNC", "target": 80, "status": "tracked",
        "note": "Proxy: PNC clients with postnatal check period recorded.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "PNC",
            "variable2": "concept_name",  "value2": "Postnatal check period"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "PNC"
        }
    },

    "mnid_pnc_extra_002": {
        "action": "add_to", "dashboard": "Maternal Health",
        "label": "HIV positive mothers identified in PNC",
        "category": "PNC", "target": 5, "status": "tracked",
        "note": "Rate: HIV Positive or Reactive among mothers with Mother HIV Status tested in PNC.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "PNC",
            "variable2": "concept_name",  "value2": "Mother HIV Status",
            "variable3": "obs_value_coded", "value3": ["Positive", "Reactive"]
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "PNC",
            "variable2": "concept_name",  "value2": "Mother HIV Status"
        }
    },

    "mnid_nb_extra_005": {
        "action": "add_to", "dashboard": "Newborn",
        "label": "Resuscitation intervention recorded",
        "category": "Newborn", "target": 80, "status": "tracked",
        "note": "Eligible newborns who received any resuscitation (bag+mask, stimulation, or documented Yes).",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Newborn",
            "variable2": "concept_name",  "value2": "Neonatal resuscitation provided",
            "variable3": "obs_value_coded", "value3": ["Yes", "Bag and mask", "Stimulation only"]
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Newborn",
            "variable2": "concept_name",  "value2": "Eligible for neonatal resuscitation"
        }
    },

    "mnid_nb_extra_006": {
        "action": "add_to", "dashboard": "Newborn",
        "label": "KMC support recorded",
        "category": "Newborn", "target": 80, "status": "tracked",
        "note": "Derived: Management given to newborn = KMC recorded in Labour encounters.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Labour",
            "variable2": "concept_name",  "value2": "Management given to newborn",
            "variable3": "obs_value_coded", "value3": "KMC"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "Labour",
            "variable2": "concept_name",  "value2": "Management given to newborn"
        }
    },

    "mnid_nb_extra_007": {
        "action": "add_to", "dashboard": "Newborn",
        "label": "Low birthweight newborns",
        "category": "Newborn", "target": 15, "status": "tracked",
        "note": "Burden indicator (lower is better). Proxy via Prematurity/Kangaroo = Low birth weight in PNC.",
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "PNC",
            "variable2": "concept_name",  "value2": "Prematurity/Kangaroo",
            "variable3": "obs_value_coded", "value3": "Low birth weight"
        },
        "denominator_filters": {
            "unique": "person_id",
            "variable1": "Service_Area", "value1": "PNC",
            "variable2": "concept_name",  "value2": "Prematurity/Kangaroo"
        }
    },
}


def apply_updates(data, definitions):
    items = data if isinstance(data, list) else [data]
    for item in items:
        if item.get("dashboard_type") != "mnid":
            continue
        inds = item.get("priority_indicators", [])
        ind_by_id = {i["id"]: i for i in inds}

        for iid, defn in definitions.items():
            if defn["action"] == "update" and iid in ind_by_id:
                target = ind_by_id[iid]
                for k, v in defn.items():
                    if k in ("action", "dashboard"):
                        continue
                    target[k] = v
                print(f"  [UPDATE] {iid}")

            elif defn["action"] == "add_to":
                if defn.get("dashboard") != item.get("report_name"):
                    continue
                if iid in ind_by_id:
                    print(f"  [SKIP-EXISTS] {iid}")
                    continue
                new_ind = {k: v for k, v in defn.items() if k not in ("action", "dashboard")}
                new_ind["id"] = iid
                inds.append(new_ind)
                ind_by_id[iid] = new_ind
                print(f"  [ADD] {iid} to {item['report_name']}")
    return data


base = os.path.join(os.path.dirname(__file__), "..", "data", "visualizations")
json_files = [
    os.path.join(base, "validated_dashboard.json"),
    os.path.join(base, "dashboards_duplicate.json"),
    os.path.join(base, "validated_dashboard_harmonized_mahis.json"),
]

for jf in json_files:
    if not os.path.exists(jf):
        print(f"SKIP (not found): {jf}")
        continue
    with open(jf, encoding="utf-8") as f:
        data = json.load(f)
    print(f"\n=== {os.path.basename(jf)} ===")
    apply_updates(data, NEW_DEFINITIONS)
    with open(jf, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Written.")

print("\nAll done.")
