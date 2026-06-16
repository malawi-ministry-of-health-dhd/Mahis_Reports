"""
MNID indicator configuration resolution.

Contains functions that build, enrich, and resolve the runtime list of
MNID indicator definitions from static config and live data schema.
"""
import pandas as pd
import logging
from mnid.chart_helpers import (
    _warn_once, _filter_columns_missing, _cov, _moving_average_values,
    _CAT_ORDER, _CAT_LABELS,
)

_LOGGER = logging.getLogger(__name__)


def _resolve_category_order(indicators: list, configured: list | None = None) -> list:
    present = {str(i.get('category', '')).strip() for i in indicators if i.get('category')}
    ordered = [c for c in (configured or _CAT_ORDER) if c in present]
    return ordered or [c for c in _CAT_ORDER if c in present]


def _uses_program_based_mnid_schema(df: pd.DataFrame) -> bool:
    if df is None or df.empty or 'Source_Program' not in df.columns:
        return False
    source_programs = set(df['Source_Program'].dropna().astype(str).str.upper().unique().tolist())
    # Needs at least one ANC/Labour/PNC program name, which only shows up in production
    # MAHIS data. Demo data uses 'MATERNAL AND CHILD HEALTH' + 'NEONATAL PROGRAM' instead,
    # so this returns False for demo and keeps program-specific derived columns
    # (mnid_labour_assessment_documented etc.) from being used when the demo schema
    # doesn't populate them.
    return bool(source_programs & {
        'ANC PROGRAM',
        'LABOUR AND DELIVERY PROGRAM',
        'PNC PROGRAM',
    })


def _program_based_priority_indicators(categories: list[str] | None = None) -> list[dict]:
    wanted = set(categories or _CAT_ORDER)
    indicators = []

    if 'ANC' in wanted:
        indicators.extend([
            {
                'id': 'mnid_anc_prog_001',
                'label': 'ANC visit documented',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Encounter_Source', 'value1': 'ANC VISIT'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_prog_002',
                'label': 'Pregnancy planned',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Pregnancy planned', 'variable2': 'obs_value_coded', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Pregnancy planned'},
            },
            {
                'id': 'mnid_anc_prog_003',
                'label': 'Gestational age method recorded',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {
                    'unique': 'person_id',
                    'variable1': 'concept_name', 'value1': 'Gestational age recorded',
                    'variable2': 'obs_value_coded', 'value2': ['GA by LNMP', 'GA by palpation', 'GA by ultrasound'],
                },
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_prog_004',
                'label': 'ANC 2+ tetanus doses',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {
                    'unique': 'person_id',
                    'variable1': 'concept_name', 'value1': 'Number of tetanus doses',
                    'variable2': 'obs_value_coded', 'value2': ['two doses', 'three doses', 'four doses'],
                },
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_prog_005',
                'label': 'Danger signs assessed',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Danger signs present'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_prog_006',
                'label': 'ANC clients tested for HIV',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_hiv_test_done', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Direct ANC HIV-testing coverage using person-level HIV test completion flags.',
            },
            {
                'id': 'mnid_anc_prog_007',
                'label': 'ANC clients with blood pressure measured',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_bp_screened', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Direct ANC blood-pressure measurement coverage using recorded systolic or diastolic values.',
            },
        ])

    if 'Labour' in wanted:
        indicators.extend([
            {
                'id': 'mnid_lab_prog_001',
                'label': 'Labour assessment documented',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'mnid_labour_assessment_documented', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Tracked from normalized labour-assessment encounter-source rows in the real parquet.',
            },
            {
                'id': 'mnid_lab_prog_001b',
                'label': 'Labour visit documented',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'mnid_labour_visit_documented', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Tracked from normalized labour-and-delivery visit encounter rows in the real parquet.',
            },
            {
                'id': 'mnid_lab_prog_002',
                'label': 'Delivery details recorded',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'concept_name', 'value2': 'Mode of delivery'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Uses presence of a delivery-mode record as the delivery-details documentation marker in the current extract.',
            },
            {
                'id': 'mnid_lab_prog_003',
                'label': 'Facility deliveries',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Place of delivery', 'variable2': 'obs_value_coded', 'value2': ['This facility', 'this facility']},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
            },
            {
                'id': 'mnid_lab_prog_004',
                'label': 'Vitamin K given at birth',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'concept_name', 'value2': 'Vitamin K given', 'variable3': 'obs_value_coded', 'value3': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'concept_name', 'value2': 'Vitamin K given'},
            },
            {
                'id': 'mnid_lab_prog_005',
                'label': 'Breastfeeding in first hour',
                'category': 'Labour',
                'target': 80,
                'status': 'awaiting_baseline',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'concept_name', 'value2': 'Breast feeding', 'variable3': 'obs_value_coded', 'value3': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'concept_name', 'value2': 'Breast feeding'},
                'note': 'Breastfeeding status is present, but the current extract does not expose the required within-1-hour timing field.',
            },
            {
                'id': 'mnid_lab_prog_006',
                'label': 'Births delivered by caesarean section',
                'category': 'Labour',
                'target': 15,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_csection', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Direct caesarean-section share among labour and delivery clients. This is a monitoring rate, not a higher-is-better coverage indicator.',
            },
            {
                'id': 'mnid_lab_prog_007',
                'label': 'Estimated blood loss recorded after delivery',
                'category': 'Labour',
                'target': 70,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'mnid_labour_estimated_blood_loss_recorded', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Operational proxy using the real Estimated blood loss concept where it is recorded in labour and delivery data.',
            },
        ])

    if 'PNC' in wanted:
        indicators.extend([
            {
                'id': 'mnid_pnc_prog_001',
                'label': 'PNC visit documented',
                'category': 'PNC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC', 'variable2': 'mnid_pnc_visit_documented', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC'},
                'note': 'Tracked from normalized PNC-visit encounter-source rows in the real parquet.',
            },
            {
                'id': 'mnid_pnc_prog_002',
                'label': 'PNC mothers within 48 hours',
                'category': 'PNC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Postnatal check period', 'variable2': 'obs_value_coded', 'value2': 'Up to 48 hrs or before discharge'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC'},
            },
            {
                'id': 'mnid_pnc_prog_003',
                'label': 'Mother alive at PNC review',
                'category': 'PNC',
                'target': 95,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Status of the mother', 'variable2': 'obs_value_coded', 'value2': ['Alive', 'Discharged alive']},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Status of the mother'},
            },
            {
                'id': 'mnid_pnc_prog_004',
                'label': 'Baby alive at PNC review',
                'category': 'PNC',
                'target': 95,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Status of baby', 'variable2': 'obs_value_coded', 'value2': 'Alive'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Status of baby'},
            },
            {
                'id': 'mnid_pnc_prog_005',
                'label': 'BCG vaccination coverage',
                'category': 'PNC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Immunisation given', 'variable2': 'obs_value_coded', 'value2': 'BCG'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Immunisation given'},
            },
            {
                'id': 'mnid_pnc_prog_006',
                'label': 'HIV positive mothers identified in PNC',
                'category': 'PNC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {
                    'unique': 'person_id',
                    'variable1': 'concept_name', 'value1': 'Mother HIV Status',
                    'variable2': 'obs_value_coded', 'value2': ['Reactive', 'Positive', 'positive', 'reactive'],
                },
                'denominator_filters': {
                    'unique': 'person_id',
                    'variable1': 'concept_name', 'value1': 'Mother HIV Status',
                },
                'note': 'Tracked from maternal HIV status observations currently flowing through the MNH parquet, pending tighter PNC encounter normalization.',
            },
        ])

    if 'Newborn' in wanted:
        indicators.extend([
            {
                'id': 'mnid_nb_prog_001',
                'label': 'Neonatal enrolment documented',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Encounter_Source', 'value1': 'NEONATAL PROGRAM'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
            },
            {
                'id': 'mnid_nb_prog_002',
                'label': 'Birth weight recorded',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Birth weight'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
            },
            {
                'id': 'mnid_nb_prog_003',
                'label': 'Gestation weeks recorded',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Gestation in weeks'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
            },
            {
                'id': 'mnid_nb_prog_004',
                'label': 'Vitamin K given',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn', 'variable2': 'concept_name', 'value2': 'Vitamin K given', 'variable3': 'obs_value_coded', 'value3': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn', 'variable2': 'concept_name', 'value2': 'Vitamin K given'},
            },
            {
                'id': 'mnid_nb_prog_005',
                'label': 'Resuscitation intervention recorded',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Neonatal resuscitation provided', 'variable2': 'obs_value_coded', 'value2': ['Yes', 'Stimulation only', 'Bag and mask']},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Neonatal resuscitation provided'},
            },
            {
                'id': 'mnid_nb_prog_006',
                'label': 'Thermal care recorded',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'thermal care'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
            },
            {
                'id': 'mnid_nb_prog_007',
                'label': 'KMC support recorded',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_kmc', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Tracked from newborn KMC support concepts already present in the current parquet.',
            },
            {
                'id': 'mnid_nb_prog_008',
                'label': 'Low birthweight newborns',
                'category': 'Newborn',
                'target': 12,
                'target_mode': 'min',
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_low_birthweight', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Birth weight'},
                'note': 'Direct low-birthweight rate from recorded birth weight bands. This is a burden rate, not a higher-is-better coverage indicator.',
            },
            {
                'id': 'mnid_nb_prog_009',
                'label': 'Birth asphyxia among newborn admissions',
                'category': 'Newborn',
                'target': 10,
                'target_mode': 'min',
                'status': 'awaiting_baseline',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_birth_asphyxia', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Needs a newborn-admission diagnosis signal for birth asphyxia in the current extract before it can be treated as a core tracked indicator.',
            },
            {
                'id': 'mnid_nb_prog_010',
                'label': 'Neonatal sepsis among newborn admissions',
                'category': 'Newborn',
                'target': 10,
                'target_mode': 'min',
                'status': 'awaiting_baseline',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_sepsis', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Needs a newborn-admission diagnosis signal for sepsis in the current extract before it can be treated as a core tracked indicator.',
            },
        ])

    return indicators


def _program_based_overlay_fallbacks(categories: list[str] | None = None) -> list[dict]:
    wanted = set(categories or _CAT_ORDER)
    indicators = []

    if 'ANC' in wanted:
        indicators.extend([
            {
                'id': 'mnid_anc_pdf_001',
                'label': 'ANC screened for anaemia',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_hb_screened', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Tracked from ANC haemoglobin screening concepts in MAHIS, including Hb(g/dL) and equivalent haemoglobin-result fields.',
            },
            {
                'id': 'mnid_anc_pdf_002',
                'label': 'ANC screened for syphilis',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_syphilis_tested', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Tracked from ANC syphilis-result concepts already present in MAHIS, including VDRL and equivalent syphilis test result fields.',
            },
            {
                'id': 'mnid_anc_pdf_003',
                'label': 'ANC clients with urinalysis performed',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_urinalysis_done', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Tracked from ANC urine-test status, urine-test-conducted, and urinalysis result concepts already present in the parquet.',
            },
            {
                'id': 'mnid_anc_pdf_004',
                'label': 'ANC screened for infection',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_infection_screened', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Tracked with an ANC infection-screening proxy built from HIV, syphilis, and malaria test fields already present in MAHIS.',
            },
            {
                'id': 'mnid_anc_pdf_005',
                'label': 'ANC screened for high blood pressure',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_bp_screened', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Tracked using ANC clients with blood-pressure vitals recorded in the current parquet.',
            },
            {
                'id': 'mnid_anc_pdf_006',
                'label': 'HIV-tested and screened for anaemia and high blood pressure',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_hiv_anaemia_bp_screened', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Tracked as a combined ANC coverage indicator using person-level HIV test, haemoglobin screening, and blood-pressure screening flags.',
            },
            {
                'id': 'mnid_anc_pdf_007',
                'label': 'POCUS with gestational age',
                'category': 'ANC',
                'target': 50,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_pocus_with_ga', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Numerator uses gestational-age-by-ultrasound plus ultrasound-status aliases where the real parquet exposes them. Denominator falls back to all ANC clients because first-visit markers are not reliable in the source extract.',
            },
        ])

    if 'Labour' in wanted:
        indicators.extend([
            {
                'id': 'mnid_lab_pdf_001',
                'label': 'Women receiving prophylactic uterotonic immediately after birth',
                'category': 'Labour',
                'target': 80,
                'status': 'awaiting_baseline',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_uterotonic_given', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Uses oxytocin and misoprostol administration concepts already present in labour records, but timing immediately after birth is not explicit in the source extract.',
            },
            {
                'id': 'mnid_lab_pdf_002',
                'label': 'Quality intrapartum care and management of complications according to guidelines',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_partograph_used', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Tracked with a labour-management proxy using documented partograph use until a fuller guideline bundle is exposed in reports data.',
            },
            {
                'id': 'mnid_lab_pdf_003',
                'label': 'Digital intrapartum monitoring in labour',
                'category': 'Labour',
                'target': 80,
                'status': 'awaiting_baseline',
                'numerator_filters': {
                    'unique': 'person_id',
                    'variable1': 'concept_name', 'value1': 'Digital intrapartum monitoring',
                    'variable2': 'obs_value_coded', 'value2': 'Used',
                },
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Awaiting a dedicated electronic fetal monitoring concept (CTG / Moyo device) in MAHIS. Partograph use is already tracked under quality intrapartum care.',
            },
            {
                'id': 'mnid_lab_pdf_004',
                'label': 'Deliveries complicated by maternal sepsis',
                'category': 'Labour',
                'target': 10,
                'target_mode': 'min',
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_maternal_sepsis', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Tracked directly from labour records with the Maternal sepsis concept. This is a burden indicator, so lower is better.',
            },
            {
                'id': 'mnid_lab_pdf_005',
                'label': 'Eligible women with pre-term labour who received antenatal corticosteroids',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_preterm_corticosteroids', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_preterm', 'value1': 'Yes'},
                'note': 'Tracked using a person-level proxy for preterm labour plus antenatal corticosteroids already captured in MAHIS labour care.',
            },
            {
                'id': 'mnid_lab_pdf_006',
                'label': 'Women in labour who received prophylactic azithromycin',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_azithromycin', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Tracked if azithromycin-specific labour prophylaxis observations are present in the reports extract.',
            },
            {
                'id': 'mnid_lab_pdf_007',
                'label': 'Women with early-detected PPH who received the WHO treatment bundle',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_pph_bundle_received', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_pph', 'value1': 'Yes'},
                'note': 'Tracked with a treatment-bundle proxy combining documented PPH plus multiple uterotonic/TXA care components already modeled in MAHIS.',
            },
        ])

    if 'Newborn' in wanted:
        indicators.extend([
            {
                'id': 'mnid_nb_pdf_001',
                'label': 'Eligible babies who received neonatal resuscitation',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {
                    'unique': 'person_id',
                    'variable1': 'mnid_newborn_asphyxia_resuscitated', 'value1': 'Yes',
                },
                'denominator_filters': {
                    'unique': 'person_id',
                    'variable1': 'mnid_newborn_birth_asphyxia', 'value1': 'Yes',
                },
                'note': 'Numerator: babies with birth asphyxia who received resuscitation. Denominator: all babies with birth asphyxia diagnosis.',
            },
            {
                'id': 'mnid_nb_pdf_002',
                'label': 'Eligible preterm and low birth-weight babies who receive iKMC',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_kmc_eligible', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_birth_weight_band', 'value1': ['1000-1499g', '1500-1999g']},
                'note': 'Tracked as an eligibility proxy using low-birth-weight bands plus KMC-related newborn care concepts already modeled in MAHIS.',
            },
            {
                'id': 'mnid_nb_pdf_003',
                'label': 'Babies between 1000-1499g who receive prophylactic CPAP',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_cpap_1000_1499', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_birth_weight_band', 'value1': '1000-1499g'},
                'note': 'Tracked using person-level birth-weight bands and CPAP treatment observations from newborn care.',
            },
            {
                'id': 'mnid_nb_pdf_004',
                'label': 'Eligible babies between 1500 and 1999g who receive CPAP',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_cpap_1500_1999', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_birth_weight_band', 'value1': '1500-1999g'},
                'note': 'Tracked using person-level birth-weight bands and CPAP treatment observations from newborn care.',
            },
            {
                'id': 'mnid_nb_pdf_005',
                'label': 'Babies with clinical jaundice who receive phototherapy',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice_phototherapy', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice', 'value1': 'Yes'},
                'note': 'Tracked using newborn jaundice observations plus phototherapy treatment observations when they land in the reports extract.',
            },
            {
                'id': 'mnid_nb_pdf_006',
                'label': 'Babies with suspected sepsis who receive parenteral antibiotics',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_sepsis_antibiotics', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_sepsis', 'value1': 'Yes'},
                'note': 'Tracked using newborn sepsis diagnosis concepts plus parenteral-antibiotic treatment observations.',
            },
            {
                'id': 'mnid_nb_pdf_007',
                'label': 'Babies not hypothermic on admission to the neonatal unit',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_not_hypothermic_admission', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Tracked when the neonatal thermal-status-on-admission concept is available in the reports extract.',
            },
            {
                'id': 'mnid_nb_pdf_008',
                'label': 'Babies not hypothermic at any time in the neonatal unit',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_not_hypothermic_anytime', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Tracked when thermal-status observations in neonatal care are available across the admission period.',
            },
        ])

    return indicators


def _enrich_program_based_mnid_indicators(indicators: list, categories: list[str] | None = None) -> list[dict]:
    wanted = set(categories or _CAT_ORDER)
    overlays = {
        'ANC screened for anaemia': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
                'variable2': 'mnid_anc_hb_screened', 'value2': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
            },
            'note': 'Tracked from ANC haemoglobin screening concepts in MAHIS, including Hb(g/dL) and equivalent haemoglobin-result fields.',
        },
        'ANC screened for infection': {
            'status': 'awaiting_baseline',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
                'variable2': 'mnid_anc_infection_screened', 'value2': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
            },
            'note': 'This is still a composite proxy built from HIV, syphilis, and malaria testing signals. Keep out of the core tracked set until a single agreed infection-screening definition is confirmed.',
        },
        'ANC screened for high blood pressure': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_anc_bp_screened', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
            },
            'note': 'Tracked using ANC clients with blood-pressure vitals recorded in the current parquet.',
        },
        'POCUS with gestational age': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
                'variable2': 'mnid_anc_pocus_with_ga', 'value2': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
            },
            'note': 'Tracked using real-parquet gestational-age-by-ultrasound rows plus ultrasound-status aliases where they are exposed.',
        },
        'HIV-tested and screened for anaemia and high blood pressure': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
                'variable2': 'mnid_anc_hiv_anaemia_bp_screened', 'value2': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
            },
            'note': 'Tracked as a combined ANC coverage indicator using person-level HIV test, haemoglobin screening, and blood-pressure screening flags.',
        },
        'Eligible babies who received neonatal resuscitation': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_resuscitation_eligible_received', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_resuscitation_eligible', 'value1': 'Yes',
            },
            'note': 'Numerator: eligible newborns with a recorded resuscitation intervention. Denominator: all newborns marked eligible for resuscitation.',
        },
        'Breastfeeding in first hour': {
            'status': 'awaiting_baseline',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Labour',
                'variable2': 'concept_name', 'value2': 'Breast feeding',
                'variable3': 'obs_value_coded', 'value3': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Labour',
                'variable2': 'concept_name', 'value2': 'Breast feeding',
            },
            'note': 'Breastfeeding status is present, but the required within-1-hour timing field is not exposed in the current extract.',
        },
        'ANC 2+ tetanus doses': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Number of tetanus doses',
                'variable2': 'obs_value_coded', 'value2': ['two doses', 'three doses', 'four doses'],
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
            },
        },
        'Pregnancy planned': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Pregnancy planned',
                'variable2': 'obs_value_coded', 'value2': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Pregnancy planned',
            },
        },
        'Danger signs assessed': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Danger signs present',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'ANC',
            },
        },
        'Facility deliveries': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_labour_facility_birth', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Labour',
            },
        },
        'Quality intrapartum care and management of complications according to guidelines': {
            'status': 'awaiting_baseline',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_labour_partograph_used', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Labour',
            },
            'note': 'Partograph use alone is too weak to stand in for the full intrapartum guideline bundle. Keep visible only as a placeholder until the bundle is modeled explicitly.',
        },
        'Digital intrapartum monitoring in labour': {
            'status': 'awaiting_baseline',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Digital intrapartum monitoring',
                'variable2': 'obs_value_coded', 'value2': 'Used',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Labour',
            },
            'note': 'Awaiting a dedicated electronic fetal monitoring concept (CTG / Moyo device) in MAHIS. Partograph use is already tracked under quality intrapartum care.',
        },
        'Eligible women with pre-term labour who received antenatal corticosteroids': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_labour_preterm_corticosteroids', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_labour_preterm', 'value1': 'Yes',
            },
            'note': 'Tracked using a person-level proxy for preterm labour plus antenatal corticosteroids already captured in MAHIS labour care.',
        },
        'Women in labour who received prophylactic azithromycin': {
            'status': 'awaiting_baseline',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_labour_azithromycin', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Labour',
            },
            'note': 'Keep pending until azithromycin prophylaxis is confirmed to land consistently in the reports extract.',
        },
        'Women with early-detected PPH who received the WHO treatment bundle': {
            'status': 'awaiting_baseline',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_labour_pph_bundle_received', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_labour_pph', 'value1': 'Yes',
            },
            'note': 'Current data supports only a treatment-bundle proxy. This needs explicit uterotonic, TXA, and timing fields before it should be treated as a core tracked indicator.',
        },
        'Vitamin K given at birth': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Labour',
                'variable2': 'concept_name', 'value2': 'Vitamin K given',
                'variable3': 'obs_value_coded', 'value3': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Labour',
                'variable2': 'concept_name', 'value2': 'Vitamin K given',
            },
        },
        'Birth weight recorded': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Birth weight',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Newborn',
            },
        },
        'Gestation weeks recorded': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Newborn',
                'variable2': 'concept_name', 'value2': 'Gestation in weeks',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Newborn',
            },
        },
        'Vitamin K given': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Newborn',
                'variable2': 'concept_name', 'value2': 'Vitamin K given',
                'variable3': 'obs_value_coded', 'value3': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Newborn',
                'variable2': 'concept_name', 'value2': 'Vitamin K given',
            },
        },
        'Thermal care recorded': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'thermal care',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Newborn',
            },
        },
        'PNC mothers within 48 hours': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Postnatal check period',
                'variable2': 'obs_value_coded', 'value2': 'Up to 48 hrs or before discharge',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'PNC',
            },
        },
        'Mother alive at PNC review': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Status of the mother',
                'variable2': 'obs_value_coded', 'value2': 'Alive',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Status of the mother',
            },
        },
        'Baby alive at PNC review': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Status of baby',
                'variable2': 'obs_value_coded', 'value2': 'Alive',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Status of baby',
            },
        },
        'BCG vaccination coverage': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Immunisation given',
                'variable2': 'obs_value_coded', 'value2': 'BCG',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Immunisation given',
            },
        },
        'HIV positive mothers identified in PNC': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Mother HIV Status',
                'variable2': 'obs_value_coded', 'value2': ['Reactive', 'Positive', 'positive', 'reactive'],
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'concept_name', 'value1': 'Mother HIV Status',
            },
            'note': 'Tracked from maternal HIV status observations currently flowing through the MNH parquet, pending tighter PNC encounter normalization.',
        },
        'Eligible preterm and low birth-weight babies who receive iKMC': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_kmc_eligible', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_birth_weight_band', 'value1': ['1000-1499g', '1500-1999g'],
            },
            'note': 'Tracked as an eligibility proxy using low-birth-weight bands plus KMC-related newborn care concepts already modeled in MAHIS.',
        },
        'Babies between 1000-1499g who receive prophylactic CPAP': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_cpap_1000_1499', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_birth_weight_band', 'value1': '1000-1499g',
            },
            'note': 'Tracked from birth-weight bands plus newborn CPAP treatment observations already normalized into the parquet.',
        },
        'Eligible babies between 1500 and 1999g who receive CPAP': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_cpap_1500_1999', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_birth_weight_band', 'value1': '1500-1999g',
            },
            'note': 'Tracked from birth-weight bands plus newborn CPAP treatment observations already normalized into the parquet. This remains a weight-band proxy because RDS is not modeled separately.',
        },
        'Babies with clinical jaundice who receive phototherapy': {
            'status': 'awaiting_baseline',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_jaundice_phototherapy', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_jaundice', 'value1': 'Yes',
            },
            'note': 'Clinical jaundice is present, but phototherapy treatment is not yet arriving in a reliable report concept in the current parquet.',
        },
        'Babies with suspected sepsis who receive parenteral antibiotics': {
            'status': 'awaiting_baseline',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_sepsis_antibiotics', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_sepsis', 'value1': 'Yes',
            },
            'note': 'Needs a linked newborn sepsis diagnosis signal in the current extract before the antibiotic-treatment ratio is dependable.',
        },
        'Babies not hypothermic on admission to the neonatal unit': {
            'status': 'tracked',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_not_hypothermic_admission', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Newborn',
            },
            'note': 'Tracked directly from the neonatal thermal-status-on-admission concept.',
        },
        'Babies not hypothermic at any time in the neonatal unit': {
            'status': 'awaiting_baseline',
            'numerator_filters': {
                'unique': 'person_id',
                'variable1': 'mnid_newborn_not_hypothermic_anytime', 'value1': 'Yes',
            },
            'denominator_filters': {
                'unique': 'person_id',
                'variable1': 'Service_Area', 'value1': 'Newborn',
            },
            'note': 'This needs longitudinal neonatal thermal-status observations, which are not yet exposed in the current parquet.',
        },
    }

    enriched = []
    seen_labels = set()
    for indicator in indicators or []:
        category = str(indicator.get('category', '')).strip()
        if wanted and category and category not in wanted:
            continue
        updated = dict(indicator)
        overlay = overlays.get(updated.get('label'))
        if overlay:
            updated.update(overlay)
        enriched.append(updated)
        seen_labels.add(updated.get('label'))

    # Keep source-of-truth indicators from JSON, but append calculable operational priorities if they are missing.
    for fallback in _program_based_priority_indicators(categories):
        if fallback.get('label') in seen_labels:
            continue
        if wanted and fallback.get('category') not in wanted:
            continue
        enriched.append(fallback)
        seen_labels.add(fallback.get('label'))

    for fallback in _program_based_overlay_fallbacks(categories):
        if fallback.get('label') in seen_labels:
            continue
        if wanted and fallback.get('category') not in wanted:
            continue
        enriched.append(fallback)
        seen_labels.add(fallback.get('label'))

    return enriched


def _resolve_runtime_mnid_indicators(indicators: list, df: pd.DataFrame, categories: list[str] | None = None) -> list:
    if _uses_program_based_mnid_schema(df):
        return _enrich_program_based_mnid_indicators(indicators, categories)
    return indicators