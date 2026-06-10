# MNID Indicator Status

This document summarizes the current status of MNID indicators in this project.

## Status Labels

- `Tracked`: implemented in the MNID dashboard and actively computed.
- `Derived`: computed from existing concepts, aliases, or person-level flags rather than one exact source concept.
- `Proxy`: usable approximation, but not a strict representation of the requested clinical definition.
- `Recorded`: relevant source concepts exist in the parquet, but the indicator is not currently promoted as a strong live KPI.
- `Awaiting baseline`: present in code or derivable in principle, but intentionally not treated as a reliable live measure yet.
- `Not currently supported`: not defensible from the current parquet without new source concepts or stronger linkage.

## ANC Indicators

| Indicator | Status | Type | Notes |
| --- | --- | --- | --- |
| ANC visit documented | Tracked | Derived | Based on ANC encounter-source rows. |
| Pregnancy planned | Tracked | Direct | Uses `Pregnancy planned`. |
| Gestational age method recorded | Tracked | Derived | Uses normalized gestational-age concepts. |
| ANC 2+ tetanus doses | Tracked | Derived | From tetanus dose values. |
| Danger signs assessed | Tracked | Direct | Uses `Danger signs present`. |
| ANC clients tested for HIV | Tracked | Derived | Uses ANC HIV testing signals. |
| ANC clients with blood pressure measured | Tracked | Derived | Uses systolic/diastolic concepts and aliases. |
| ANC screened for anaemia | Tracked | Derived | Uses `Hb(g/dL)` and haemoglobin aliases. |
| ANC screened for syphilis | Tracked | Derived | Uses `Syphilis Test Result` and VDRL aliases. |
| ANC clients with urinalysis performed | Tracked | Derived | Uses urine-test status and urinalysis concepts. |
| ANC screened for infection | Awaiting baseline | Proxy | Composite proxy from HIV, syphilis, and malaria testing. |
| ANC screened for high blood pressure | Tracked | Derived | Uses BP screening observations and BP vitals. |
| HIV-tested and screened for anaemia and high blood pressure | Tracked | Derived | Composite ANC coverage indicator. |
| POCUS with gestational age | Tracked | Proxy | Uses ultrasound-status aliases plus GA-by-ultrasound logic. |
| Proportion of HIV-positive pregnant women receiving ART during pregnancy and/or labour | Not currently supported | Not defensible | HIV status exists; ART exposure is not yet reliably supported in the parquet. |
| Proportion of pregnant women receiving IPTp-SP | Not currently supported | Not defensible | No defensible IPTp-SP concept path yet. |

## Labour / Intrapartum Indicators

| Indicator | Status | Type | Notes |
| --- | --- | --- | --- |
| Labour assessment documented | Tracked | Derived | Uses normalized `Labour assessment` encounter-source rows. |
| Labour visit documented | Tracked | Derived | Uses normalized `Labour and delivery visit` rows. |
| Delivery details recorded | Tracked | Proxy | Uses delivery-mode presence as the documentation marker. |
| Facility deliveries | Tracked | Direct | Based on `Place of delivery`. |
| Vitamin K given at birth | Tracked | Direct | Uses labour-side Vitamin K concept when present. |
| Births delivered by caesarean section | Tracked | Direct | Uses `Mode of delivery = Caesarean section`. |
| Estimated blood loss recorded after delivery | Tracked | Proxy | Operational proxy from `Estimated blood loss`. |
| Deliveries complicated by maternal sepsis | Tracked | Derived | Uses `Maternal sepsis = Yes`. Lower is better. |
| Eligible women with pre-term labour who received antenatal corticosteroids | Tracked | Derived | Uses preterm-labour plus corticosteroid concepts. |
| Breastfeeding in first hour | Awaiting baseline | Proxy | Breastfeeding status exists; timing within one hour does not. |
| Women receiving prophylactic uterotonic immediately after birth | Awaiting baseline | Proxy | Uterotonic concepts exist, but “immediately after birth” timing is not explicit. |
| Quality intrapartum care and management of complications according to guidelines | Awaiting baseline | Proxy | Current proxy is too weak for a full guideline bundle. |
| Digital intrapartum monitoring in labour | Awaiting baseline | Not defensible yet | No robust digital monitoring concept in current source parquet. |
| Women in labour who received prophylactic azithromycin | Awaiting baseline | Proxy | Concept path exists, but source consistency remains weak. |
| Women with early-detected PPH who received the WHO treatment bundle | Awaiting baseline | Proxy | Bundle proxy exists, but not strong enough for a core KPI. |
| Proportion of women with suspected maternal sepsis managed using the FAST-M protocol | Not currently supported | Not defensible | No explicit FAST-M bundle/protocol concept set. |
| Proportion of deliveries with objective blood loss measurement using calibrated drape | Not currently supported | Not defensible | Only generic estimated blood-loss recording exists. |

## PNC Indicators

| Indicator | Status | Type | Notes |
| --- | --- | --- | --- |
| PNC visit documented | Tracked | Derived | Uses normalized `Pnc visit` encounter-source rows. |
| PNC mothers within 48 hours | Tracked | Direct | Uses `Postnatal check period`. |
| Mother alive at PNC review | Tracked | Direct | Counts `Alive` and `Discharged alive`. |
| Baby alive at PNC review | Tracked | Direct | Uses `Status of baby`. |
| BCG vaccination coverage | Tracked | Derived | Uses `Immunisation given = BCG`. |
| HIV positive mothers identified in PNC | Tracked | Derived | Uses maternal HIV status concepts. |
| Maternal deaths occurring in health facilities | Recorded | Proxy candidate | Relevant outcome structure exists, but current real parquet does not show defensible death values. |

## Newborn / Neonatal Indicators

| Indicator | Status | Type | Notes |
| --- | --- | --- | --- |
| Neonatal enrolment documented | Tracked | Derived | Uses neonatal encounter presence. |
| Birth weight recorded | Tracked | Direct | Uses birth weight. |
| Gestation weeks recorded | Tracked | Derived | Uses normalized gestation-week concepts. |
| Vitamin K given | Tracked | Direct | Uses newborn-side Vitamin K concept. |
| Resuscitation intervention recorded | Tracked | Derived | Uses normalized neonatal resuscitation concepts. |
| Thermal care recorded | Tracked | Derived | Uses normalized `thermal care`. |
| KMC support recorded | Tracked | Derived | Uses KMC-related newborn care concepts. |
| Low birthweight newborns | Tracked | Direct | Burden indicator from birth weight bands. Lower is better. |
| Eligible babies who received neonatal resuscitation | Tracked | Derived | Uses eligibility plus intervention observations. |
| Eligible preterm and low birth-weight babies who receive iKMC | Tracked | Derived | Uses birth-weight bands and KMC concepts. |
| Babies between 1000-1499g who receive prophylactic CPAP | Tracked | Derived | Uses weight band plus CPAP support observations. |
| Eligible babies between 1500 and 1999g who receive CPAP | Tracked | Proxy | Weight-band proxy; RDS is not modeled separately. |
| Babies not hypothermic on admission to the neonatal unit | Tracked | Direct | Uses thermal-status-on-admission observations. |
| Birth asphyxia among newborn admissions | Awaiting baseline | Proxy | Diagnosis signal exists, but denominator still needs stronger admission definition. |
| Neonatal sepsis among newborn admissions | Awaiting baseline | Proxy | Same denominator-strength issue as above. |
| Babies with clinical jaundice who receive phototherapy | Awaiting baseline | Proxy | Jaundice/treatment logic exists, but source consistency is still weak. |
| Babies with suspected sepsis who receive parenteral antibiotics | Awaiting baseline | Proxy | Needs stronger linkage between diagnosis and treatment. |
| Babies not hypothermic at any time in the neonatal unit | Awaiting baseline | Proxy | Needs longitudinal thermal observations across stay. |
| Severe neonatal jaundice admission proportion | Not currently supported | Not defensible | No robust severe-jaundice diagnosis path. |
| Neonatal mortality rate | Recorded | Proxy candidate | Outcome-related concepts exist in places, but not strongly enough for a reliable live KPI. |

## Summary by State

### Tracked

- ANC visit documented
- Pregnancy planned
- Gestational age method recorded
- ANC 2+ tetanus doses
- Danger signs assessed
- ANC clients tested for HIV
- ANC clients with blood pressure measured
- ANC screened for anaemia
- ANC screened for syphilis
- ANC clients with urinalysis performed
- ANC screened for high blood pressure
- HIV-tested and screened for anaemia and high blood pressure
- POCUS with gestational age
- Labour assessment documented
- Labour visit documented
- Delivery details recorded
- Facility deliveries
- Vitamin K given at birth
- Births delivered by caesarean section
- Estimated blood loss recorded after delivery
- Deliveries complicated by maternal sepsis
- Eligible women with pre-term labour who received antenatal corticosteroids
- PNC visit documented
- PNC mothers within 48 hours
- Mother alive at PNC review
- Baby alive at PNC review
- BCG vaccination coverage
- HIV positive mothers identified in PNC
- Neonatal enrolment documented
- Birth weight recorded
- Gestation weeks recorded
- Vitamin K given
- Resuscitation intervention recorded
- Thermal care recorded
- KMC support recorded
- Low birthweight newborns
- Eligible babies who received neonatal resuscitation
- Eligible preterm and low birth-weight babies who receive iKMC
- Babies between 1000-1499g who receive prophylactic CPAP
- Eligible babies between 1500 and 1999g who receive CPAP
- Babies not hypothermic on admission to the neonatal unit

### Awaiting baseline / development-stage

- ANC screened for infection
- Breastfeeding in first hour
- Women receiving prophylactic uterotonic immediately after birth
- Quality intrapartum care and management of complications according to guidelines
- Digital intrapartum monitoring in labour
- Women in labour who received prophylactic azithromycin
- Women with early-detected PPH who received the WHO treatment bundle
- Birth asphyxia among newborn admissions
- Neonatal sepsis among newborn admissions
- Babies with clinical jaundice who receive phototherapy
- Babies with suspected sepsis who receive parenteral antibiotics
- Babies not hypothermic at any time in the neonatal unit

### Recorded but not yet promoted as strong live KPIs

- Maternal deaths occurring in health facilities
- Neonatal mortality rate

### Not currently supported

- ART during pregnancy/labour indicator
- IPTp-SP indicator
- FAST-M maternal sepsis management
- Objective blood-loss measurement with calibrated drape
- Severe neonatal jaundice admission proportion

## Interpretation

- `Tracked` indicators are the ones safe to present as current live MNID dashboard measures.
- `Awaiting baseline` indicators are visible development-stage metrics and should not be treated as final operational KPIs.
- `Recorded` means the parquet contains some relevant data, but the project is intentionally not claiming the indicator is fully defensible yet.
- `Not currently supported` means the current parquet cannot safely support the requested definition.
