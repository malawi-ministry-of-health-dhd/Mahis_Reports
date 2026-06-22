"""
MNID indicator configuration resolution.

Contains functions that build, enrich, and resolve the runtime list of
MNID indicator definitions from static config and live data schema.
"""
import pandas as pd
import logging
from mnid.charts.chart_helpers import (
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
                'id': 'mnid_anc_overview_001',
                'label': 'ANC Visits',
                'category': 'ANC',
                'target': 80,
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_anc_visit_documented', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_overview_002',
                'label': 'ANC Complications',
                'category': 'ANC',
                'target': 15,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_anc_complication', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_overview_003',
                'label': 'ANC Clients Not Admissioned to Labour',
                'category': 'ANC',
                'target': 35,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_anc_not_reaching_labour', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_anc_visit_documented', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_anc_prog_007',
                'label': 'Blood pressure measured',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_bp_screened', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_pdf_001',
                'label': 'Screened for anaemia',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_hb_screened', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_prog_006',
                'label': 'Tested for HIV',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_hiv_test_done', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_pdf_002',
                'label': 'Screened for syphilis',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_syphilis_tested', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_pdf_003',
                'label': 'Screened for urinary tract infections',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_urinalysis_done', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
            },
            {
                'id': 'mnid_anc_pdf_007',
                'label': 'Gestational age assessed using ultrasound/POCUS',
                'category': 'ANC',
                'target': 50,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_pocus_with_ga', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Uses GA by ultrasound recording as the primary signal; POCUS-completed concept included where present.',
            },
            {
                'id': 'mnid_anc_prog_008',
                'label': 'At least 4 ANC contacts',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_anc_4plus_contacts', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Counts distinct ANC visit dates per person; persons with ≥4 distinct dates are flagged.',
            },
            {
                'id': 'mnid_anc_prog_004',
                'label': 'Tetanus doses (2+)',
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
                'id': 'mnid_anc_pdf_004',
                'label': 'Screened for infection',
                'category': 'ANC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC', 'variable2': 'mnid_anc_infection_screened', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'ANC'},
                'note': 'Composite: HIV tested OR syphilis tested OR MRDT tested — reflects any infection-screening pathway.',
            },
        ])

    if 'Labour' in wanted:
        indicators.extend([
            {
                'id': 'mnid_lab_overview_001',
                'label': 'Labour & Delivery Visits',
                'category': 'Labour',
                'target': 80,
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_visit_documented', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
            },
            {
                'id': 'mnid_lab_overview_002',
                'label': 'Labour Complications',
                'category': 'Labour',
                'target': 15,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_complication', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_visit_documented', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_lab_overview_003',
                'label': 'Labour Clients Not Admissioned to PNC',
                'category': 'Labour',
                'target': 35,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_not_reaching_pnc', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_visit_documented', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_lab_overview_004',
                'label': 'Live Births',
                'category': 'Labour',
                'target': 95,
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_live_birth', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_visit_documented', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_lab_overview_005',
                'label': 'Stillbirths',
                'category': 'Labour',
                'target': 5,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_stillbirth', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_visit_documented', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_nb_overview_001',
                'label': 'Outborn babies',
                'category': 'Newborn',
                'target': 10,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_outborn', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
            },
            {
                'id': 'mnid_lab_prog_008',
                'label': 'Partograph use',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'mnid_labour_partograph_used', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Partograph documentation is the proxy for intrapartum monitoring (paper or digital).',
            },
            {
                'id': 'mnid_lab_prog_007',
                'label': 'Deliveries with objective blood loss measurement',
                'category': 'Labour',
                'target': 70,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'mnid_labour_estimated_blood_loss_recorded', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Any documented blood loss value (Estimated blood loss concept) counts as objective measurement.',
            },
            {
                'id': 'mnid_lab_prog_009',
                'label': 'Women with imminent preterm birth receiving ACs',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_preterm_corticosteroids', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_preterm', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_lab_prog_010',
                'label': 'Eligible women receiving antibiotic prophylaxis',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour', 'variable2': 'mnid_labour_antibiotic_prophylaxis', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Covers azithromycin prophylaxis and surgical antibiotic prophylaxis (ampicillin, cefazolin, benzylpenicillin).',
            },
            {
                'id': 'mnid_lab_prog_006',
                'label': 'Overall caesarean section rate',
                'category': 'Labour',
                'target': 15,
                'target_mode': 'min',
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_csection', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Monitoring rate — lower limit 15% reflects CEmONC access threshold. Emergency versus elective caesarean section split is still awaiting data.',
            },
            {
                'id': 'mnid_lab_pdf_001',
                'label': 'Uterotonic given after birth',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_uterotonic_given', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Oxytocin or misoprostol documented in the labour episode. Timing relative to birth is not captured.',
            },
            {
                'id': 'mnid_lab_prog_011',
                'label': 'Immediate skin-to-skin care for newborn',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_skin_to_skin', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Proxy: thermal care recorded at neonatal enrolment (which follows delivery) OR thermal status = Not hypothermic on admission.',
            },
            {
                'id': 'mnid_lab_prog_012',
                'label': 'Newborns not breathing at birth receiving bag-mask ventilation',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_resuscitation_eligible_received', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_resuscitation_eligible', 'value1': 'Yes'},
                'note': 'Eligible for neonatal resuscitation flag as denominator; resuscitation given as numerator. Within-1-minute timing not captured.',
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
                'id': 'mnid_lab_pdf_004',
                'label': 'Maternal sepsis rate',
                'category': 'Labour',
                'target': 10,
                'target_mode': 'min',
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_maternal_sepsis', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Burden rate — lower is better.',
            },
            {
                'id': 'mnid_lab_pdf_007',
                'label': 'PPH with WHO treatment bundle',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_pph_bundle_received', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_pph', 'value1': 'Yes'},
                'note': 'Bundle proxy: PPH identified AND ≥2 of oxytocin / TXA / misoprostol documented.',
            },
            {
                'id': 'mnid_lab_prog_013',
                'label': 'Pre-eclampsia/eclampsia receiving magnesium sulphate',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_magnesium_sulphate', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_labour_eclampsia', 'value1': 'Yes'},
                'note': 'Tracked from magnesium sulphate administration documented in the labour episode.',
            },
            {
                'id': 'mnid_lab_prog_014',
                'label': 'Birth weight recorded',
                'category': 'Labour',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Birth weight'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Labour'},
                'note': 'Uses birth weight documentation linked to the delivery episode or immediate newborn record for the same client.',
            },
        ])

    if 'PNC' in wanted:
        indicators.extend([
            {
                'id': 'mnid_pnc_overview_001',
                'label': 'PNC Visits',
                'category': 'PNC',
                'target': 80,
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_pnc_visit_documented', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC'},
            },
            {
                'id': 'mnid_pnc_overview_002',
                'label': 'Mother Complications',
                'category': 'PNC',
                'target': 15,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_pnc_mother_complication', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_pnc_visit_documented', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_pnc_overview_003',
                'label': 'Newborn Complications',
                'category': 'PNC',
                'target': 15,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_pnc_newborn_complication', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_pnc_visit_documented', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_pnc_overview_004',
                'label': 'Maternal Deaths',
                'category': 'PNC',
                'target': 1,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_pnc_maternal_death', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_pnc_mother_status_recorded', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_pnc_overview_005',
                'label': 'Newborn Deaths',
                'category': 'PNC',
                'target': 1,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_pnc_newborn_death', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_pnc_baby_status_recorded', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_pnc_prog_007',
                'label': 'Early initiation of breastfeeding within 1 hour of birth',
                'category': 'PNC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC', 'variable2': 'mnid_pnc_breastfeeding_initiated', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC'},
                'note': 'Tracks breastfeeding initiation documented in the labour or PNC episode. Exact within-1-hour timing is not yet explicitly captured in the extract.',
            },
            {
                'id': 'mnid_pnc_prog_008',
                'label': 'Birth weight assessed',
                'category': 'PNC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC', 'variable2': 'mnid_pnc_birth_weight_assessed', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC'},
                'note': 'Proxy via Prematurity/Kangaroo concept at PNC visit (records Low birth weight / Normal weight category).',
            },
            {
                'id': 'mnid_pnc_prog_009',
                'label': 'Blood pressure measured during PNC',
                'category': 'PNC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC', 'variable2': 'mnid_pnc_bp_measured', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC'},
                'note': 'Tracked from systolic and diastolic blood pressure concepts documented in PNC records.',
            },
            {
                'id': 'mnid_pnc_prog_010',
                'label': 'Temperature of mother measured during PNC',
                'category': 'PNC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC', 'variable2': 'mnid_pnc_temperature_measured', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC'},
                'note': 'Tracked from maternal temperature concepts documented in PNC records.',
            },
            {
                'id': 'mnid_pnc_prog_011',
                'label': 'Vitamin K at birth',
                'category': 'PNC',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC', 'variable2': 'mnid_pnc_vitamin_k_at_birth', 'value2': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'PNC'},
                'note': 'Vitamin K given documented at labour/delivery or neonatal enrolment, carried forward to PNC via person-level flag.',
            },
        ])

    if 'Newborn' in wanted:
        indicators.extend([
            {
                'id': 'mnid_nb_overview_002',
                'label': 'Neonatal Deaths',
                'category': 'Newborn',
                'target': 5,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_neonatal_death', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_status_recorded', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_nb_overview_003',
                'label': 'Neonatal Complications at Birth',
                'category': 'Newborn',
                'target': 15,
                'target_mode': 'min',
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_complication_at_birth', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
            },
            {
                'id': 'mnid_nb_overview_004',
                'label': 'iKMC Initiated',
                'category': 'Newborn',
                'target': 80,
                'status': 'overview_only',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_kmc', 'value1': 'Yes'},
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
                'note': 'Burden rate — lower is better.',
            },
            {
                'id': 'mnid_nb_prog_009',
                'label': 'Birth asphyxia among newborn admissions',
                'category': 'Newborn',
                'target': 10,
                'target_mode': 'min',
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_birth_asphyxia', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Burden rate — proxied from birth asphyxia suspected and resuscitation-eligibility concepts.',
            },
            {
                'id': 'mnid_nb_prog_010',
                'label': 'Neonatal sepsis among newborn admissions',
                'category': 'Newborn',
                'target': 10,
                'target_mode': 'min',
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_sepsis', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Burden rate — proxied from sepsis-related observation concepts.',
            },
            {
                'id': 'mnid_nb_prog_011',
                'label': 'Pulse oximeter used at admission',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_pulse_oximeter_admission', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Tracked using pulse oximeter or oxygen saturation documentation captured at neonatal admission.',
            },
            {
                'id': 'mnid_nb_prog_012',
                'label': 'Babies who had bilirubin measured',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_bilirubin_measured', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Tracked from bilirubin-related measurement concepts documented in newborn care.',
            },
            {
                'id': 'mnid_nb_prog_013',
                'label': 'Babies with jaundice who had bilirubin measured',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice_bilirubin_measured', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice', 'value1': 'Yes'},
                'note': 'Uses clinical jaundice plus bilirubin-measurement documentation in the newborn record.',
            },
            {
                'id': 'mnid_nb_prog_014',
                'label': 'Babies with jaundice receiving phototherapy',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice_phototherapy', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice', 'value1': 'Yes'},
                'note': 'Uses clinical jaundice and phototherapy treatment documentation as the newborn jaundice care pathway proxy.',
            },
            {
                'id': 'mnid_nb_prog_015',
                'label': 'Babies breastfed within 1 hour',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_pnc_breastfeeding_initiated', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Uses breastfeeding initiation documented around birth and carried as a person-level flag into the newborn pathway.',
            },
        ])

    return indicators


def _program_based_overlay_fallbacks(categories: list[str] | None = None) -> list[dict]:
    """Supplementary PDF-aligned indicators appended if not already covered by the prog set."""
    wanted = set(categories or _CAT_ORDER)
    indicators = []

    if 'Newborn' in wanted:
        indicators.extend([
            {
                'id': 'mnid_nb_pdf_001',
                'label': 'Eligible babies who received neonatal resuscitation',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_asphyxia_resuscitated', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_birth_asphyxia', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_nb_pdf_002',
                'label': 'Eligible preterm and low birth-weight babies who receive iKMC',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_kmc_eligible', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_birth_weight_band', 'value1': ['1000-1499g', '1500-1999g']},
            },
            {
                'id': 'mnid_nb_pdf_003',
                'label': 'Babies between 1000-1499g who receive prophylactic CPAP',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_cpap_1000_1499', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_birth_weight_band', 'value1': '1000-1499g'},
            },
            {
                'id': 'mnid_nb_pdf_005',
                'label': 'Babies with clinical jaundice who receive phototherapy',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice_phototherapy', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice', 'value1': 'Yes'},
                'note': 'Jaundice identification used as phototherapy proxy (MAHIS clinical jaundice → phototherapy care pathway).',
            },
            {
                'id': 'mnid_nb_pdf_006',
                'label': 'Babies with suspected sepsis who receive parenteral antibiotics',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_sepsis_antibiotics', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_sepsis', 'value1': 'Yes'},
            },
            {
                'id': 'mnid_nb_pdf_007',
                'label': 'Babies not hypothermic on admission',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_not_hypothermic_admission', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
            },
            {
                'id': 'mnid_nb_pdf_008',
                'label': 'Babies not hypothermic at any time in the neonatal unit',
                'category': 'Newborn',
                'target': 80,
                'status': 'tracked',
                'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_not_hypothermic_anytime', 'value1': 'Yes'},
                'denominator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'},
                'note': 'Proxy from admission thermal status — longitudinal stay temperature not yet in extract.',
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
