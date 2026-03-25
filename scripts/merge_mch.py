"""Script to merge MCH entry from rep/dashboards8.json into validated_dashboard.json with MNID fields."""
import json, os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with open('data/visualizations/validated_dashboard.json') as f:
    dash_data = json.load(f)

with open('rep/dashboards8.json') as f:
    rep_data = json.load(f)

mch = next(d for d in rep_data if 'Maternal' in d['report_name'])

mch['dashboard_type'] = 'mnid'

mch['visualization_types']['priority_indicators'] = [
    {
        "id": "mnid_pi_001", "label": "Tetanus 2+ Doses", "target": 80,
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Number of tetanus doses",
            "variable2": "Value", "value2": ["two doses", "three doses", "four doses"]
        },
        "denominator_filters": {"unique": "person_id", "variable1": "Encounter", "value1": "ANC VISIT"}
    },
    {
        "id": "mnid_pi_002", "label": "Facility Deliveries", "target": 80,
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Place of delivery",
            "variable2": "obs_value_coded", "value2": ["This facility", "this facility"]
        },
        "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Place of delivery"}
    },
    {
        "id": "mnid_pi_003", "label": "Skilled Delivery", "target": 80,
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Staff conducting delivery"
        },
        "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Mode of delivery"}
    },
    {
        "id": "mnid_pi_004", "label": "PNC Within 48 Hours", "target": 80,
        "numerator_filters": {
            "unique": "person_id",
            "variable1": "concept_name", "value1": "Postnatal check period",
            "variable2": "obs_value_coded", "value2": "Up to 48 hrs or before discharge"
        },
        "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Postnatal check period"}
    },
    {
        "id": "mnid_pi_005", "label": "BCG Coverage", "target": 90,
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
    }
]

mch['visualization_types']['care_phases'] = [
    {
        "title": "Antenatal Care", "color": "green",
        "metrics": [
            {
                "label": "Tetanus 2+ Doses", "target": 80,
                "numerator_filters": {
                    "unique": "person_id",
                    "variable1": "concept_name", "value1": "Number of tetanus doses",
                    "variable2": "Value", "value2": ["two doses", "three doses", "four doses"]
                },
                "denominator_filters": {"unique": "person_id", "variable1": "Encounter", "value1": "ANC VISIT"}
            },
            {
                "label": "HIV Testing in ANC", "target": 95,
                "numerator_filters": {
                    "unique": "person_id", "variable1": "concept_name", "value1": "HIV Test"
                },
                "denominator_filters": {"unique": "person_id", "variable1": "Encounter", "value1": "ANC VISIT"}
            }
        ]
    },
    {
        "title": "Labour and Delivery", "color": "violet",
        "metrics": [
            {
                "label": "Facility Deliveries", "target": 80,
                "numerator_filters": {
                    "unique": "person_id",
                    "variable1": "concept_name", "value1": "Place of delivery",
                    "variable2": "obs_value_coded", "value2": ["This facility", "this facility"]
                },
                "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Place of delivery"}
            },
            {
                "label": "Skilled Delivery", "target": 80,
                "numerator_filters": {
                    "unique": "person_id", "variable1": "concept_name", "value1": "Staff conducting delivery"
                },
                "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Mode of delivery"}
            },
            {
                "label": "Live Births", "target": 85,
                "numerator_filters": {
                    "unique": "person_id",
                    "variable1": "concept_name", "value1": "Outcome of the delivery",
                    "variable2": "obs_value_coded", "value2": ["Live births", "live births"]
                },
                "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Outcome of the delivery"}
            }
        ]
    },
    {
        "title": "Postnatal Care", "color": "pink",
        "metrics": [
            {
                "label": "PNC Mothers Within 48 Hours", "target": 80,
                "numerator_filters": {
                    "unique": "person_id",
                    "variable1": "concept_name", "value1": "Postnatal check period",
                    "variable2": "obs_value_coded", "value2": "Up to 48 hrs or before discharge"
                },
                "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Postnatal check period"}
            },
            {
                "label": "BCG Coverage", "target": 90,
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
            }
        ]
    },
    {
        "title": "Newborn Outcomes", "color": "orange",
        "metrics": [
            {
                "label": "Vitamin K at Birth", "target": 90,
                "numerator_filters": {
                    "unique": "person_id",
                    "variable1": "concept_name", "value1": "Vitamin K given",
                    "variable2": "obs_value_coded", "value2": ["Yes", "yes"]
                },
                "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Vitamin K given"}
            },
            {
                "label": "Exclusive Breastfeeding", "target": 80,
                "numerator_filters": {
                    "unique": "person_id",
                    "variable1": "concept_name", "value1": "Breast feeding",
                    "variable2": "obs_value_coded", "value2": ["Exclusive", "exclusive breastfeeding"]
                },
                "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Breast feeding"}
            }
        ]
    },
    {
        "title": "Maternal Outcomes", "color": "lime",
        "metrics": [
            {
                "label": "Mothers Alive at Discharge", "target": 99,
                "numerator_filters": {
                    "unique": "person_id",
                    "variable1": "concept_name", "value1": "Status of the mother",
                    "variable2": "obs_value_coded", "value2": ["Alive", "alive"]
                },
                "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Status of the mother"}
            },
            {
                "label": "Babies Alive at Discharge", "target": 99,
                "numerator_filters": {
                    "unique": "person_id",
                    "variable1": "concept_name", "value1": "Status of baby",
                    "variable2": "obs_value_coded", "value2": ["Alive", "alive"]
                },
                "denominator_filters": {"unique": "person_id", "variable1": "concept_name", "value1": "Status of baby"}
            }
        ]
    }
]

dash_data = [d for d in dash_data if 'Maternal' not in d['report_name']]
dash_data.append(mch)

with open('data/visualizations/validated_dashboard.json', 'w') as f:
    json.dump(dash_data, f, indent=2)

print('Done. Dashboards:', [d['report_name'] for d in dash_data])
