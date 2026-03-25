# MNID Indicator Definitions and Calculation Logic
> Status: **DRAFT** — indicators marked ⏳ are awaiting concept name verification from OpenMRS.
> Update concept names once confirmed from the OpenMRS data dictionary.
> Last updated: 2026-03-25

---

## Colour Logic

| Coverage vs Target     | CSS Class | Badge Label   |
|------------------------|-----------|---------------|
| ≥ 100% of target       | `ok`      | On target     |
| 85–99% of target       | `warn`    | Performing    |
| < 85% of target        | `danger`  | Needs review  |
| Awaiting baseline      | —         | Awaiting baseline |

---

## ANC Indicators (6 total, 1 tracked)

| ID            | Label                            | Numerator Filter                                                                 | Denominator Filter                    | Target | Status |
|---------------|----------------------------------|---------------------------------------------------------------------------------|---------------------------------------|--------|--------|
| mnid_anc_001  | ANC screened for anaemia         | `concept_name = "Screening for anaemia"` OR `"Haemoglobin level"` (any value)  | `Encounter = "ANC VISIT"`             | 80%    | ⏳ Awaiting baseline |
| mnid_anc_002  | ANC screened for infection       | `concept_name = "Screening for infection"` OR STI concept (any value)           | `Encounter = "ANC VISIT"`             | 80%    | ⏳ Awaiting baseline |
| mnid_anc_003  | ANC screened for high BP         | `concept_name = "Blood pressure reading"` OR `"Systolic blood pressure"` (any) | `Encounter = "ANC VISIT"`             | 80%    | ⏳ Awaiting baseline |
| mnid_anc_004  | HIV-tested + screened for anaemia + BP | Composite: patient has HIV test AND anaemia screening AND BP in same ANC visit  | `Encounter = "ANC VISIT"`             | 80%    | ⏳ Awaiting baseline |
| mnid_anc_005  | POCUS with gestational age recorded | `concept_name = "Gestational age"` OR `"POCUS performed"` (any value)        | `Encounter = "ANC VISIT"`             | 50%    | ⏳ Awaiting baseline |
| mnid_anc_006  | ANC 2+ tetanus doses             | `concept_name = "Number of tetanus doses"` AND `Value IN ["two doses","three doses","four doses"]` | `Encounter = "ANC VISIT"` | 80% | ✅ Tracked |

**Formula (all):** `(unique person_id with numerator condition / unique person_id with denominator condition) × 100`

---

## Labour & Delivery Indicators (7 total, 2 tracked)

| ID            | Label                            | Numerator Filter                                                                    | Denominator Filter                              | Target | Status |
|---------------|----------------------------------|------------------------------------------------------------------------------------|-------------------------------------------------|--------|--------|
| mnid_lab_001  | Intrapartum care per guidelines  | Composite: PPH, Sepsis, PET/ET, Obstructed labour — all managed per protocol       | All labour encounters                           | 80%    | ⏳ Awaiting baseline |
| mnid_lab_002  | Digital intrapartum monitoring   | `concept_name = "Partograph used"` OR `"Digital monitoring"` (any value)          | Labour encounters                               | 70%    | ⏳ Awaiting baseline |
| mnid_lab_003  | Antenatal corticosteroids        | `concept_name = "Antenatal corticosteroids given"` (eligible pre-term cases)       | Labour encounters with gestational age < 37wk  | 70%    | ⏳ Awaiting baseline |
| mnid_lab_004  | Prophylactic azithromycin        | `concept_name = "Azithromycin given"` (in labour)                                 | Labour encounters                               | 50%    | ⏳ Awaiting baseline — pending Malawi guideline adoption |
| mnid_lab_005  | PPH early detection + treatment  | `concept_name = "PPH treatment bundle"` OR `"Postpartum hemorrhage"` managed      | Labour encounters                               | 70%    | ⏳ Awaiting baseline |
| mnid_lab_006  | Facility deliveries              | `concept_name = "Place of delivery"` AND `obs_value_coded IN ["This facility","this facility"]` | `concept_name = "Place of delivery"` | 80% | ✅ Tracked |
| mnid_lab_007  | Skilled delivery attendance      | `concept_name = "Staff conducting delivery"` (any value present)                  | `concept_name = "Mode of delivery"`             | 80%    | ✅ Tracked |

---

## Newborn Care Indicators (8 total, 0 tracked)

All 8 require birth weight capture and/or separate neonatal unit admission records not yet confirmed in OpenMRS.

| ID           | Label                                    | Numerator Filter                                                              | Denominator Filter                          | Target | Status |
|--------------|------------------------------------------|------------------------------------------------------------------------------|---------------------------------------------|--------|--------|
| mnid_nb_001  | Neonatal resuscitation (eligible babies) | `concept_name = "Neonatal resuscitation"` OR `"Management given to newborn" = "Neonatal resuscitation"` | Babies requiring resuscitation | 80%    | ⏳ Awaiting baseline |
| mnid_nb_002  | iKMC (preterm/LBW babies)               | `concept_name = "Kangaroo mother care"` OR `"Prematurity/Kangaroo"` (any)   | Preterm or LBW babies                       | 80%    | ⏳ Awaiting baseline |
| mnid_nb_003  | Prophylactic CPAP (1000–1499g)           | `concept_name = "CPAP support provided"` AND birth weight 1000–1499g         | Babies born 1000–1499g                     | 80%    | ⏳ Awaiting baseline |
| mnid_nb_004  | CPAP for eligible babies (1500–1999g)    | `concept_name = "CPAP support provided"` AND birth weight 1500–1999g         | Babies born 1500–1999g                     | 80%    | ⏳ Awaiting baseline |
| mnid_nb_005  | Phototherapy for jaundice                | `concept_name = "Phototherapy given"` (any value)                            | Babies with clinical jaundice               | 80%    | ⏳ Awaiting baseline |
| mnid_nb_006  | Parenteral antibiotics for sepsis        | `concept_name = "Management given to newborn"` = parenteral antibiotic, OR DISPENSING record | Babies with suspected sepsis | 80%    | ⏳ Awaiting baseline |
| mnid_nb_007  | Babies not hypothermic on NNU admission  | `concept_name = "Thermal status on admission"` = `"Not hypothermic"`        | NNU admissions                              | 80%    | ⏳ Awaiting baseline |
| mnid_nb_008  | Babies not hypothermic at any time       | Longitudinal: all temperature readings within stay = normal range            | NNU admissions (all temperature records)   | 80%    | ⏳ Awaiting baseline |

---

## PNC Indicators (3 total, 3 tracked)

| ID            | Label                   | Numerator Filter                                                                      | Denominator Filter                             | Target | Status |
|---------------|-------------------------|---------------------------------------------------------------------------------------|------------------------------------------------|--------|--------|
| mnid_pnc_001  | PNC mothers within 48h  | `concept_name = "Postnatal check period"` AND `obs_value_coded = "Up to 48 hrs or before discharge"` | `concept_name = "Postnatal check period"` | 80% | ✅ Tracked |
| mnid_pnc_002  | BCG vaccination coverage | `concept_name IN ["Type of immunization the baby received","Immunisation given"]` AND `obs_value_coded IN ["BCG","bcg"]` | Same concept_name (any value) | 90% | ✅ Tracked |
| mnid_pnc_003  | Exclusive breastfeeding | `concept_name = "Breast feeding"` AND `obs_value_coded IN ["Exclusive","exclusive breastfeeding"]` | `concept_name = "Breast feeding"` | 80% | ✅ Tracked |

---

## Calculation Pattern

All indicators follow the same pattern:

```
coverage_pct = (COUNT DISTINCT unique_key WHERE numerator conditions) /
               (COUNT DISTINCT unique_key WHERE denominator conditions)
               × 100
```

- `unique_key` is always `person_id` (one person counted once per indicator)
- Filtering happens after date-range and facility filters applied by `home.py`
- Multi-value conditions use `IN [...]` matching (case-sensitive unless noted)

---

## How to Activate an Awaiting-Baseline Indicator

Once the concept name is confirmed from OpenMRS:

1. Update `data/visualizations/validated_dashboard.json` — find the indicator by `id` and:
   - Change `"status": "awaiting_baseline"` → `"status": "tracked"`
   - Remove the `"note"` field
   - Add `"numerator_filters"` and `"denominator_filters"` blocks:

```json
{
  "id": "mnid_anc_001",
  "label": "ANC screened for anaemia",
  "category": "ANC",
  "target": 80,
  "status": "tracked",
  "numerator_filters": {
    "unique": "person_id",
    "variable1": "concept_name",
    "value1": "Screening for anaemia",
    "variable2": "obs_value_coded",
    "value2": "Done"
  },
  "denominator_filters": {
    "unique": "person_id",
    "variable1": "Encounter",
    "value1": "ANC VISIT"
  }
}
```

2. The dashboard will automatically start computing the indicator on next load.

---

## Summary

| Category         | Total | Tracked | Awaiting Baseline |
|------------------|-------|---------|-------------------|
| ANC              | 6     | 1       | 5                 |
| Labour & Delivery| 7     | 2       | 5                 |
| Newborn          | 8     | 0       | 8                 |
| PNC              | 3     | 3       | 0                 |
| **Total**        | **24**| **6**   | **18**            |
