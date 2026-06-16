"""MNID dataframe preparation and serialization helpers."""

import json
import os
import re
import uuid
import numpy as np
import pandas as pd
pd.options.mode.chained_assignment = None

# Lightweight in-memory store for the two active DataFrames the trend and
# compare callbacks need (fallback when aggregate is not yet built).
# Only ever holds 2 entries, so we skip disk files and eviction logic.
_MNID_UI_CACHE: dict = {}


def _remember_ui_payload(prefix: str, records_or_fn, stable_key: str | None = None) -> str:
    cache_key = f'{prefix}:{stable_key}' if stable_key else f'{prefix}:{uuid.uuid4().hex}'
    if cache_key in _MNID_UI_CACHE:
        return cache_key
    records = records_or_fn() if callable(records_or_fn) else records_or_fn
    _MNID_UI_CACHE[cache_key] = records
    return cache_key


def _restore_ui_dataframe(cache_key: str | None) -> pd.DataFrame:
    if not cache_key:
        return pd.DataFrame()
    obj = _MNID_UI_CACHE.get(cache_key)
    if isinstance(obj, pd.DataFrame):
        return obj
    return deserialize_store_df(obj)

from .constants import (
    ALL_DISTRICTS,
    ALL_FACILITIES,
    FACILITY_COORDS,
    FACILITY_DISTRICT,
    FACILITY_NAMES,
)


_PROGRAM_SERVICE_AREA_MAP = {
    'ANC PROGRAM': 'ANC',
    'LABOUR AND DELIVERY PROGRAM': 'Labour',
    'PNC PROGRAM': 'PNC',
    'NEONATAL PROGRAM': 'Newborn',
}

_SERVICE_AREA_ALIASES = {
    'ANC': 'ANC',
    'ANC PROGRAM': 'ANC',
    'LABOUR': 'Labour',
    'LABOUR AND DELIVERY PROGRAM': 'Labour',
    'PNC': 'PNC',
    'PNC PROGRAM': 'PNC',
    'NEONATAL': 'Newborn',
    'NEONATAL PROGRAM': 'Newborn',
    'NEWBORN': 'Newborn',
}

_CONCEPT_ALIASES = {
    'VItamin K Given?': 'Vitamin K given',
    'Vitamin K given?': 'Vitamin K given',
    'HIV test': 'HIV Test',
    'MRDT': 'mRDT results',
    'Hemoglobin': 'Hb(g/dL)',
    'Mother VDRL/Syphilis result': 'Syphilis Test Result',
    'Gestation weeks': 'Gestation in weeks',
    'Resuscitation method': 'Neonatal resuscitation provided',
    'Resuscitation attempt': 'Neonatal resuscitation provided',
    'Resuscitation Type': 'Neonatal resuscitation provided',
    'Type of resuscitation': 'Neonatal resuscitation provided',
    'Breast feeding in the first hour of birth': 'Breast feeding',
    'Gestation age to be used': 'Gestational age recorded',
    'Ultrasound scan status': 'POCUS completed',
    'Antenatal corticosteroids': 'Antenatal corticosteroids given',
    'Jaundice': 'Clinical jaundice',
    'Is the visit within': 'Postnatal check period',
    'Date BCG given': 'Immunisation given',
}

_OBS_VALUE_ALIASES = {
    'Bag Valve Mask Ventilation (BVM)': 'Bag and mask',
    'Stimulation': 'Stimulation only',
    'Bacille camile-guerin vaccination': 'BCG',
    'CPAP(Continuous Positive  Airway Pressure)': 'CPAP',
    'Continuous KMC': 'Kangaroo mother care',
    'Intermittent KMC': 'Kangaroo mother care',
    'Admit to KMC': 'Kangaroo mother care',
    'this facility': 'This facility',
    'ga by ultrasound': 'GA by ultrasound',
    'Ga by palpation': 'GA by palpation',
    'Caesarean Section': 'Caesarean section',
    'Ultrasound scan not done': 'No',
    'if within phototherapy level of bilirubin – phototherapy': 'Phototherapy',
}


def _derive_contextual_concepts(out: pd.DataFrame) -> pd.DataFrame:
    if out.empty or 'concept_name' not in out.columns:
        return out

    def _cstr(col: str) -> pd.Series:
        if col not in out.columns:
            return pd.Series('', index=out.index)
        s = out[col].fillna('').astype('category')
        s = s.cat.rename_categories(dict(zip(s.cat.categories, s.cat.categories.astype(str).str.strip())))
        return s.astype(str)

    concept_series = _cstr('concept_name')
    obs_series     = _cstr('obs_value_coded')
    val_series     = _cstr('Value')
    combined_value = obs_series.where(obs_series.ne(''), val_series)

    treatment_thermal = concept_series.eq('Treatment') & combined_value.str.fullmatch('Thermal Care', case=False, na=False)
    out.loc[treatment_thermal, 'concept_name'] = 'thermal care'

    treatment_cpap = concept_series.eq('Treatment') & combined_value.str.fullmatch('CPAP', case=False, na=False)
    out.loc[treatment_cpap, 'concept_name'] = 'CPAP support'

    treatment_phototherapy = concept_series.eq('Treatment') & combined_value.str.contains('phototherapy', case=False, na=False)
    out.loc[treatment_phototherapy, 'concept_name'] = 'Phototherapy given'

    presenting_jaundice = concept_series.eq('Presenting complaint') & combined_value.str.fullmatch('jaundice', case=False, na=False)
    out.loc[presenting_jaundice, 'concept_name'] = 'Clinical jaundice'

    oxygen_cpap = concept_series.eq('Oxygen Therapy') & combined_value.str.contains('cpap', case=False, na=False)
    out.loc[oxygen_cpap, 'concept_name'] = 'CPAP support'

    ultrasound_reason = concept_series.eq('Reason ultrasound not done') & combined_value.ne('')
    out.loc[ultrasound_reason, 'concept_name'] = 'POCUS completed'
    out.loc[ultrasound_reason, 'obs_value_coded'] = 'No'

    return out


def _first_numeric(series: pd.Series) -> float | None:
    for value in series:
        if value is None or pd.isna(value):
            continue
        if isinstance(value, (int, float)):
            if pd.notna(value):
                return float(value)
        text = str(value).strip()
        if not text:
            continue
        match = re.search(r'(\d+(?:\.\d+)?)', text.replace(',', ''))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _birth_weight_band(weight_g: float | None) -> str:
    if weight_g is None:
        return ''
    if 1000 <= weight_g <= 1499:
        return '1000-1499g'
    if 1500 <= weight_g <= 1999:
        return '1500-1999g'
    if 2000 <= weight_g <= 2499:
        return '2000-2499g'
    if weight_g < 1000:
        return '<1000g'
    return '>=2500g'


def _normalize_birth_weight_g(weight: float | None) -> float | None:
    if weight is None:
        return None
    # Neonatal birth weight in the parquet is often stored as kilograms in ValueN.
    if 0 < weight <= 10:
        return weight * 1000
    return weight


def _derive_person_level_context(out: pd.DataFrame) -> pd.DataFrame:
    if out.empty or 'person_id' not in out.columns:
        return out

    def _cat_str(col: str, transform=None) -> pd.Series:
        """Build a categorical string series from out[col].

        Categorical means str.contains/str.lower etc. only run on the unique values,
        not every row - about 50x faster when there are far fewer distinct concept/obs
        values than rows.
        """
        if col not in out.columns:
            return pd.Series('', index=out.index)
        s = out[col].fillna('').astype('category')
        cats = s.cat.categories.astype(str).str.strip()
        if transform:
            cats = transform(cats)
        s = s.cat.rename_categories(dict(zip(s.cat.categories, cats)))
        return s.astype(str)

    concept  = _cat_str('concept_name')
    obs      = _cat_str('obs_value_coded')
    value    = _cat_str('Value')
    value_n  = pd.to_numeric(out['ValueN'], errors='coerce') if 'ValueN' in out.columns else pd.Series(np.nan, index=out.index)
    service  = _cat_str('Service_Area')
    encounter = _cat_str('Encounter')
    program  = _cat_str('Program', transform=lambda s: s.str.upper())
    combined = obs.where(obs.ne(''), value)
    concept_lower   = concept.str.lower()
    combined_lower  = combined.str.lower()
    encounter_upper = encounter.str.upper()
    encounter_source = _cat_str('Encounter_Source') if 'Encounter_Source' in out.columns else encounter
    encounter_source_lower = encounter_source.str.lower()

    person_ctx = pd.DataFrame({'person_id': out['person_id'].dropna().astype(str).unique()})

    def _assign_flag(name: str, mask: pd.Series) -> None:
        if len(mask) != len(out):
            return
        people = set(out.loc[mask.fillna(False), 'person_id'].dropna().astype(str))
        person_ctx[name] = person_ctx['person_id'].isin(people).map({True: 'Yes', False: ''})

    def _ctx_series(name: str) -> pd.Series:
        if name in person_ctx.columns:
            return person_ctx[name].fillna('').astype(str)
        return pd.Series('', index=person_ctx.index)

    anc_mask = service.eq('ANC')
    labour_mask = service.eq('Labour')
    pnc_mask = service.eq('PNC')
    newborn_mask = service.eq('Newborn')
    labour_like_mask = (
        labour_mask
        | encounter_upper.str.contains('LABOUR|DELIVERY|BIRTH', na=False)
        | program.isin(['LABOUR AND DELIVERY PROGRAM'])
    )

    # Each str.contains/regex check costs ~215-340ms on 100k rows, so we compute them
    # all once up front rather than re-running them inside every _assign_flag call.
    _cp_hiv = (concept.isin(['HIV Test', 'HIV status', 'HIV Positive', 'Mother HIV Status', 'New HIV status'])
               | concept_lower.str.contains('hiv', na=False))
    _cp_hb = (concept.isin(['Hb(g/dL)', 'Last HB result', 'Hemoglobin', 'Haemoglobin', 'Anemia screening'])
              | concept_lower.str.contains('hb\\(g/dl\\)|hemoglobin|haemoglobin|anemia screening', regex=True, na=False))
    _cp_syphilis = (concept.isin(['Syphilis Test Result', 'Mother VDRL/Syphilis result'])
                    | concept_lower.str.contains('syphilis', na=False))
    _cp_mrdt = (concept.isin(['mRDT results', 'Malaria Test Result', 'Malaria Parasites Result'])
                | concept_lower.str.contains('mrdt|malaria test result|malaria parasites result', regex=True, na=False))
    _cp_partograph_exact = concept.isin(['Was a partograph used', 'Was a partograph used?'])
    _cp_partograph_fuzzy = concept_lower.str.contains('partograph', na=False)
    _cp_obs_complications = concept.isin(['Obstetric complications'])
    _cp_preterm_fuzzy = concept_lower.str.contains('preterm labour', na=False)
    _cp_corticosteroid = (concept.isin(['Antenatal corticosteroids', 'Antenatal corticosteroids given', 'Corticosteroids'])
                          | concept_lower.str.contains('corticosteroid', na=False))
    _cp_obstetric_comp_fuzzy = concept_lower.str.contains('obstetric complication', na=False)
    _cv_pph = combined_lower.str.contains('post partum haemorrhage|pph', regex=True, na=False)
    _cp_obstetric_care = (concept.isin(['Obstetric Care', 'Obstetric Care provided'])
                          | concept_lower.str.contains('obstetric care', na=False))
    _cp_azithromycin = (concept.isin(['Prophylactic azithromycin given'])
                        | concept_lower.str.contains('azithromycin', na=False)
                        | combined_lower.str.contains('azithromycin', na=False))
    _cp_kmc = (concept.isin(['iKMC initiated', 'Prematurity/Kangaroo', 'Management given to newborn'])
               | concept_lower.str.contains('kmc|kangaroo', regex=True, na=False)
               | combined_lower.str.contains('kangaroo mother care|continuous kmc|intermittent kmc|admit to kmc', regex=True, na=False))
    _cp_cpap = (concept.isin(['CPAP support'])
                | concept_lower.str.contains('cpap', na=False)
                | combined_lower.str.contains('cpap', na=False))
    _cp_phototherapy = (concept.isin(['Phototherapy given'])
                        | concept_lower.str.contains('phototherapy', na=False)
                        | combined_lower.str.contains('phototherapy', na=False))
    _cp_jaundice = (concept.isin(['Clinical jaundice'])
                    | concept_lower.str.contains('jaundice', na=False)
                    | combined_lower.str.contains('jaundice', na=False))
    _cv_asphyxia = combined_lower.str.contains('asphyxia', na=False)
    _cp_sepsis = (concept.isin(['Neonatal Sepsis - Early Onset', 'Neonatal Sepsis - Late Onset'])
                  | concept_lower.str.contains('sepsis', na=False))
    _cp_antibiotics = (concept.isin(['Parenteral antibiotics given', 'Management given to newborn'])
                       | concept_lower.str.contains('antibiotic', na=False)
                       | combined_lower.str.contains('antibiotic', na=False))

    _assign_flag(
        'mnid_anc_hiv_test_done',
        anc_mask & _cp_hiv & ~combined_lower.isin(['', 'not done', 'unknown']),
    )
    _assign_flag(
        'mnid_anc_hb_screened',
        anc_mask & (
            (concept.eq('Anemia screening') & combined_lower.eq('yes'))
            | (_cp_hb & ~concept.eq('Anemia screening') & ~combined_lower.isin(['', 'not done']))
        ),
    )
    _assign_flag(
        'mnid_anc_syphilis_tested',
        anc_mask & _cp_syphilis & ~combined_lower.isin(['', 'not done', 'unknown']),
    )
    _assign_flag(
        'mnid_anc_urinalysis_done',
        anc_mask & (
            (concept.eq('Urine test status') & combined_lower.eq('urine test conducted'))
            | concept.eq('Urine Test Conducted')
            | concept.isin(['Urine protein', 'Urinalysis protein', 'Urinalysis glucose', 'Urinalysis leucocytes', 'Urinalysis nitrites'])
        ),
    )
    _assign_flag(
        'mnid_anc_mrdt_tested',
        anc_mask & _cp_mrdt & ~combined_lower.isin(['', 'not done', 'unknown']),
    )
    _assign_flag(
        'mnid_anc_bp_screened',
        anc_mask & (
            concept.isin(['Systolic blood pressure', 'Diastolic blood pressure', 'Systolic', 'Diastolic', 'Blood Pressure'])
            | (concept.eq('High blood pressure screening') & combined_lower.eq('yes'))
        ),
    )
    _assign_flag(
        'mnid_anc_pocus_completed',
        anc_mask & concept.eq('POCUS completed') & combined_lower.isin(['yes', 'done', 'completed']),
    )
    _assign_flag(
        'mnid_anc_ga_ultrasound',
        anc_mask & concept.eq('Gestational age recorded') & combined_lower.eq('ga by ultrasound'),
    )

    _assign_flag(
        'mnid_labour_partograph_used',
        labour_mask & ((_cp_partograph_exact & combined_lower.eq('yes')) | _cp_partograph_fuzzy),
    )
    _assign_flag(
        'mnid_labour_preterm',
        labour_mask & ((_cp_obs_complications & combined_lower.eq('preterm labour')) | _cp_preterm_fuzzy),
    )
    _assign_flag(
        'mnid_labour_corticosteroids',
        labour_mask & _cp_corticosteroid & combined_lower.ne(''),
    )
    _assign_flag(
        'mnid_labour_pph',
        labour_mask & (
            (concept.isin(['PPH']) & ~combined_lower.isin(['', 'no', 'negative']))
            | ((_cp_obs_complications | _cp_obstetric_comp_fuzzy) & _cv_pph)
        ),
    )
    _assign_flag(
        'mnid_labour_facility_birth',
        labour_mask & concept.eq('Place of delivery') & combined_lower.eq('this facility'),
    )
    _assign_flag(
        'mnid_labour_csection',
        labour_mask & concept.eq('Mode of delivery') & combined_lower.eq('caesarean section'),
    )
    _assign_flag(
        'mnid_labour_eclampsia',
        labour_mask & _cp_obs_complications & combined_lower.eq('eclampsia'),
    )
    _assign_flag(
        'mnid_labour_obstructed_labour',
        labour_mask & _cp_obs_complications & combined_lower.eq('obstructed labour'),
    )
    _assign_flag(
        'mnid_labour_stillbirth',
        labour_mask
        & concept.eq('Outcome of the delivery')
        & combined_lower.isin(['fresh still birth', 'macerated still birth']),
    )
    _assign_flag(
        'mnid_labour_estimated_blood_loss_recorded',
        (labour_like_mask | program.isin(['ANC PROGRAM']))
        & concept.eq('Estimated blood loss')
        & (~combined_lower.isin(['', 'none', 'nan']) | value_n.notna()),
    )
    _assign_flag(
        'mnid_labour_assessment_documented',
        labour_mask & encounter_source_lower.eq('labour assessment'),
    )
    _assign_flag(
        'mnid_labour_visit_documented',
        labour_mask & encounter_source_lower.eq('labour and delivery visit'),
    )
    _assign_flag(
        'mnid_labour_maternal_sepsis',
        labour_like_mask
        & concept.eq('Maternal sepsis')
        & combined_lower.eq('yes'),
    )
    _assign_flag(
        'mnid_labour_pph_oxytocin',
        labour_like_mask
        & concept.isin(['Oxytocin 10 iu given', 'Oxytocin 20iu in 1000ml ns or rl over 4 hrs'])
        & combined_lower.eq('yes'),
    )
    _assign_flag(
        'mnid_labour_pph_txa',
        labour_like_mask
        & concept.eq('1g Tranexamic Acid IV slow push over 10 minutes')
        & combined_lower.eq('yes'),
    )
    _assign_flag(
        'mnid_labour_pph_misoprostol',
        labour_like_mask
        & concept_lower.str.contains('misoprostol', na=False)
        & combined_lower.eq('yes'),
    )
    obstetric_care = labour_mask & _cp_obstetric_care
    _assign_flag('mnid_labour_azithromycin', labour_mask & _cp_azithromycin)

    _assign_flag(
        'mnid_pnc_hiv_test_positive',
        pnc_mask & (
            (concept.eq('Mother HIV Status') & combined_lower.eq('positive'))
            | (concept.eq('New HIV status') & combined_lower.eq('positive'))
        ),
    )
    _assign_flag(
        'mnid_pnc_visit_documented',
        pnc_mask & encounter_source_lower.eq('pnc visit'),
    )
    _assign_flag(
        'mnid_pnc_maternal_death',
        pnc_mask & concept.eq('Status of the mother') & combined_lower.isin(['death', 'died', 'dead', 'deceased']),
    )

    _assign_flag(
        'mnid_newborn_kmc',
        newborn_mask & (
            (concept.eq('iKMC initiated') & combined_lower.eq('yes'))
            | (concept.eq('Prematurity/Kangaroo') & combined_lower.isin(['kmc', 'kangaroo mother care']))
            | (concept.eq('Management given to newborn') & combined_lower.isin(['kmc', 'kangaroo mother care']))
        ),
    )
    _assign_flag(
        'mnid_newborn_cpap',
        newborn_mask & (
            concept.eq('CPAP support')
            & combined_lower.isin(['bubble cpap', 'cpap'])
        ),
    )
    _assign_flag(
        'mnid_newborn_phototherapy',
        newborn_mask & concept.eq('Phototherapy given') & combined_lower.eq('yes'),
    )
    _assign_flag('mnid_newborn_jaundice', newborn_mask & _cp_jaundice)
    _assign_flag(
        'mnid_newborn_birth_asphyxia',
        newborn_mask & (
            (concept.eq('Birth asphyxia suspected') & combined_lower.eq('yes'))
            | (concept.isin(['Known medical condition', 'Primary diagnosis', 'Secondary diagnosis',
                             'Presenting complaint', 'Neonatal admission diagnosis', 'Diagnosis'])
               & _cv_asphyxia
               & ~combined_lower.isin(['no', 'none', '']))
        ),
    )
    _assign_flag(
        'mnid_newborn_resuscitation_given',
        newborn_mask & (
            concept.isin(['Neonatal resuscitation provided'])
            & combined_lower.isin([
                'yes', 'stimulation only', 'bag and mask',
                'suctioning', 'oxygen',
                'cardio pulmonary resuscitation (cpr)',
            ])
            & ~combined_lower.isin(['none', 'unknown', ''])
        ),
    )
    _assign_flag(
        'mnid_newborn_resuscitation_eligible',
        newborn_mask
        & concept.eq('Eligible for neonatal resuscitation')
        & combined_lower.eq('yes'),
    )
    _assign_flag('mnid_newborn_sepsis', newborn_mask & _cp_sepsis)
    _assign_flag(
        'mnid_newborn_parenteral_antibiotics',
        newborn_mask
        & (
            (concept.eq('Parenteral antibiotics given') & combined_lower.eq('yes'))
            | ((concept.eq('Management given to newborn')) & combined_lower.eq('antibiotics'))
        ),
    )
    _assign_flag(
        'mnid_newborn_oxygen_available',
        newborn_mask & concept.eq('Oxygen available at facility') & combined_lower.eq('yes'),
    )
    _assign_flag(
        'mnid_newborn_can_measure_oxygen_saturation',
        newborn_mask & concept.eq('Can measure oxygen saturation') & combined_lower.eq('yes'),
    )
    _assign_flag(
        'mnid_newborn_not_hypothermic_admission',
        newborn_mask & concept.eq('Thermal status on admission') & combined_lower.eq('not hypothermic'),
    )
    _assign_flag(
        'mnid_newborn_not_hypothermic_anytime',
        newborn_mask & (
            (concept.eq('Thermal status on admission') & combined_lower.eq('not hypothermic'))
            | combined_lower.eq('not hypothermic')
        ),
    )

    pph_component_cols = ['mnid_labour_pph_oxytocin', 'mnid_labour_pph_txa', 'mnid_labour_pph_misoprostol']
    pph_component_score = person_ctx[pph_component_cols].eq('Yes').sum(axis=1)
    person_ctx['mnid_labour_pph_bundle_proxy'] = (pph_component_score >= 2).map({True: 'Yes', False: ''})

    person_ctx['mnid_anc_infection_screened'] = (
        _ctx_series('mnid_anc_hiv_test_done').eq('Yes')
        | _ctx_series('mnid_anc_syphilis_tested').eq('Yes')
        | _ctx_series('mnid_anc_mrdt_tested').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_anc_hiv_anaemia_bp_screened'] = (
        _ctx_series('mnid_anc_hiv_test_done').eq('Yes')
        & _ctx_series('mnid_anc_hb_screened').eq('Yes')
        & _ctx_series('mnid_anc_bp_screened').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_anc_pocus_with_ga'] = (
        _ctx_series('mnid_anc_ga_ultrasound').eq('Yes')
        | _ctx_series('mnid_anc_pocus_completed').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_labour_preterm_corticosteroids'] = (
        _ctx_series('mnid_labour_preterm').eq('Yes')
        & _ctx_series('mnid_labour_corticosteroids').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_labour_pph_bundle_received'] = (
        _ctx_series('mnid_labour_pph').eq('Yes')
        & _ctx_series('mnid_labour_pph_bundle_proxy').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_labour_uterotonic_given'] = (
        _ctx_series('mnid_labour_pph_oxytocin').eq('Yes')
        | _ctx_series('mnid_labour_pph_misoprostol').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_newborn_asphyxia_resuscitated'] = (
        _ctx_series('mnid_newborn_birth_asphyxia').eq('Yes')
        & _ctx_series('mnid_newborn_resuscitation_given').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_newborn_resuscitation_eligible_received'] = (
        _ctx_series('mnid_newborn_resuscitation_eligible').eq('Yes')
        & _ctx_series('mnid_newborn_resuscitation_given').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_newborn_jaundice_phototherapy'] = (
        _ctx_series('mnid_newborn_jaundice').eq('Yes')
        & _ctx_series('mnid_newborn_phototherapy').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_newborn_sepsis_antibiotics'] = (
        _ctx_series('mnid_newborn_sepsis').eq('Yes')
        & _ctx_series('mnid_newborn_parenteral_antibiotics').eq('Yes')
    ).map({True: 'Yes', False: ''})

    # Pulls birth weight in one vectorized pass instead of looping row by row and
    # building a pd.Series per row, which got slow once there were a lot of rows.
    birth_weight_rows = out.loc[concept.eq('Birth weight'), ['person_id']].copy()
    if not birth_weight_rows.empty:
        value_numeric = out['ValueN'] if 'ValueN' in out.columns else pd.Series([None] * len(out), index=out.index)
        bw_vn = pd.to_numeric(value_numeric.loc[birth_weight_rows.index], errors='coerce')
        needs_parse = bw_vn.isna()
        if needs_parse.any():
            str_vals = obs.loc[birth_weight_rows.index].where(
                obs.loc[birth_weight_rows.index].ne(''),
                value.loc[birth_weight_rows.index],
            )
            parsed = str_vals.str.extract(r'(\d+(?:\.\d+)?)')[0]
            bw_vn = bw_vn.fillna(pd.to_numeric(parsed, errors='coerce'))
        birth_weight_rows['mnid_birth_weight_g'] = bw_vn.apply(_normalize_birth_weight_g)
    else:
        birth_weight_rows['mnid_birth_weight_g'] = pd.Series(dtype=float)

    birth_weight_map = (
        birth_weight_rows.dropna(subset=['mnid_birth_weight_g'])
        .groupby('person_id', as_index=False)['mnid_birth_weight_g']
        .first()
    )
    if not birth_weight_map.empty:
        birth_weight_map['person_id'] = birth_weight_map['person_id'].astype(str)
        birth_weight_map['mnid_birth_weight_band'] = birth_weight_map['mnid_birth_weight_g'].apply(_birth_weight_band)
        person_ctx = person_ctx.merge(birth_weight_map, on='person_id', how='left')
    else:
        person_ctx['mnid_birth_weight_g'] = pd.NA
        person_ctx['mnid_birth_weight_band'] = ''

    person_ctx['mnid_newborn_cpap_1000_1499'] = (
        _ctx_series('mnid_newborn_cpap').eq('Yes')
        & _ctx_series('mnid_birth_weight_band').eq('1000-1499g')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_newborn_cpap_1500_1999'] = (
        _ctx_series('mnid_newborn_cpap').eq('Yes')
        & _ctx_series('mnid_birth_weight_band').eq('1500-1999g')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_newborn_kmc_eligible'] = (
        _ctx_series('mnid_newborn_kmc').eq('Yes')
        & _ctx_series('mnid_birth_weight_band').isin(['1000-1499g', '1500-1999g'])
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_newborn_low_birthweight'] = (
        _ctx_series('mnid_birth_weight_band').isin(['1000-1499g', '1500-1999g', '2000-2499g'])
    ).map({True: 'Yes', False: ''})

    person_ctx['person_id'] = person_ctx['person_id'].astype(str)
    merged = out
    merged['person_id'] = merged['person_id'].astype(str)
    return merged.merge(person_ctx, on='person_id', how='left')


def _derive_service_area_vectorized(df: pd.DataFrame) -> pd.Series:
    program = df['Program'].fillna('').astype(str).str.strip().str.upper() if 'Program' in df.columns else pd.Series('', index=df.index)
    encounter = df['Encounter'].fillna('').astype(str).str.strip().str.upper() if 'Encounter' in df.columns else pd.Series('', index=df.index)

    from_program = program.map(_PROGRAM_SERVICE_AREA_MAP).fillna('')
    enc_newborn = encounter.str.contains('NEONATAL', na=False)
    enc_pnc     = encounter.str.contains('PNC|POSTNATAL', na=False)
    enc_labour  = encounter.str.contains('LABOUR|DELIVERY|BIRTH', na=False)
    enc_anc     = encounter.str.contains('ANC|PREGNANCY|OBSTETRIC', na=False)

    return pd.Series(
        np.select(
            [from_program.ne(''), enc_newborn, enc_pnc, enc_labour, enc_anc],
            [from_program,        'Newborn',   'PNC',   'Labour',   'ANC'],
            default='',
        ),
        index=df.index,
    )


def _derive_service_area(row: pd.Series) -> str:
    program = str(row.get('Program') or '').strip().upper()
    encounter = str(row.get('Encounter') or '').strip().upper()

    if program in _PROGRAM_SERVICE_AREA_MAP:
        return _PROGRAM_SERVICE_AREA_MAP[program]
    if 'NEONATAL' in encounter:
        return 'Newborn'
    if 'PNC' in encounter or 'POSTNATAL' in encounter:
        return 'PNC'
    if 'LABOUR' in encounter or 'DELIVERY' in encounter or 'BIRTH' in encounter:
        return 'Labour'
    if 'ANC' in encounter or 'PREGNANCY' in encounter or 'OBSTETRIC' in encounter:
        return 'ANC'
    return ''


def _normalize_reporting_program(service_area: pd.Series) -> pd.Series:
    return service_area.map({
        'ANC': 'MATERNAL AND CHILD HEALTH',
        'Labour': 'MATERNAL AND CHILD HEALTH',
        'PNC': 'MATERNAL AND CHILD HEALTH',
        'Newborn': 'NEONATAL PROGRAM',
    }).fillna('')


def _canonicalize_service_area(series: pd.Series) -> pd.Series:
    cleaned = series.fillna('').astype(str).str.strip()
    upper = cleaned.str.upper()
    mapped = upper.map(_SERVICE_AREA_ALIASES).fillna('')
    return mapped.where(mapped.ne(''), cleaned)


_ENCOUNTER_LABEL_MAP = {
    'ANC': 'ANC VISIT',
    'Labour': 'LABOUR AND DELIVERY',
    'PNC': 'POSTNATAL CARE',
    'Newborn': 'NEONATAL CARE',
}


def _normalize_encounter(row: pd.Series) -> str:
    service_area = str(row.get('Service_Area') or '').strip()
    encounter = str(row.get('Encounter') or '').strip()
    if service_area == 'ANC':
        return 'ANC VISIT'
    if service_area == 'Labour':
        return 'LABOUR AND DELIVERY'
    if service_area == 'PNC':
        return 'POSTNATAL CARE'
    if service_area == 'Newborn':
        return 'NEONATAL CARE'
    return encounter


def _normalize_mnid_semantics(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    out = df
    if 'Program' in out.columns and 'Source_Program' not in out.columns:
        out['Source_Program'] = out['Program']

    if 'concept_name' in out.columns:
        concept_series = out['concept_name'].fillna('').astype(str).str.strip()
        out['concept_name'] = concept_series.replace(_CONCEPT_ALIASES)

    if 'obs_value_coded' in out.columns:
        obs_series = out['obs_value_coded'].fillna('').astype(str).str.strip()
        out['obs_value_coded'] = obs_series.replace(_OBS_VALUE_ALIASES)

    # The new parquet stores several clinically relevant coded answers in `Value`.
    if {'obs_value_coded', 'Value'}.issubset(out.columns):
        obs_blank = out['obs_value_coded'].fillna('').astype(str).str.strip().eq('')
        val_present = out['Value'].fillna('').astype(str).str.strip().ne('')
        out.loc[obs_blank & val_present, 'obs_value_coded'] = (
            out.loc[obs_blank & val_present, 'Value']
            .fillna('')
            .astype(str)
            .str.strip()
            .replace(_OBS_VALUE_ALIASES)
        )

    out = _derive_contextual_concepts(out)

    service_area = _derive_service_area_vectorized(out)
    if 'Service_Area' in out.columns:
        existing = _canonicalize_service_area(out['Service_Area'])
        derived = _canonicalize_service_area(service_area)
        out['Service_Area'] = existing.where(existing.ne(''), derived)
    else:
        out['Service_Area'] = _canonicalize_service_area(service_area)

    reporting_program = _normalize_reporting_program(out['Service_Area'])
    if 'Reporting_Program' in out.columns:
        existing = out['Reporting_Program'].fillna('').astype(str).str.strip()
        existing_norm = _normalize_reporting_program(_canonicalize_service_area(existing))
        out['Reporting_Program'] = existing_norm.where(existing_norm.ne(''), reporting_program)
    else:
        out['Reporting_Program'] = reporting_program

    if 'Encounter' in out.columns:
        out['Encounter_Source'] = out['Encounter']
        mapped_enc = out['Service_Area'].map(_ENCOUNTER_LABEL_MAP)
        out['Encounter'] = mapped_enc.where(mapped_enc.notna(), out['Encounter'])

    return _derive_person_level_context(out)


def register_facility_metadata(df: pd.DataFrame) -> None:
    """Update live facility metadata caches from the current MNID dataframe."""
    if df is None or df.empty:
        return

    def _clean(s: pd.Series) -> pd.Series:
        return s.fillna('').astype(str).str.strip()

    if {'Facility_CODE', 'Facility'}.issubset(df.columns):
        fac_meta = df[['Facility_CODE', 'Facility']].dropna().drop_duplicates()
        codes = _clean(fac_meta['Facility_CODE'])
        names = _clean(fac_meta['Facility'])
        valid = codes.ne('') & names.ne('')
        new_map = dict(zip(codes[valid], names[valid]))
        FACILITY_NAMES.update(new_map)
        for code in new_map:
            if code not in ALL_FACILITIES:
                ALL_FACILITIES.append(code)

    if {'Facility_CODE', 'District'}.issubset(df.columns):
        dist_meta = df[['Facility_CODE', 'District']].dropna().drop_duplicates()
        codes = _clean(dist_meta['Facility_CODE'])
        districts = _clean(dist_meta['District'])
        valid = codes.ne('') & districts.ne('')
        new_dist = dict(zip(codes[valid], districts[valid]))
        FACILITY_DISTRICT.update(new_dist)
        for district in new_dist.values():
            if district not in ALL_DISTRICTS:
                ALL_DISTRICTS.append(district)

    if {'Facility_CODE', 'Facility', 'District'}.issubset(df.columns):
        combo = df[['Facility_CODE', 'Facility', 'District']].dropna().drop_duplicates()
        codes = _clean(combo['Facility_CODE'])
        names = _clean(combo['Facility'])
        dists = _clean(combo['District'])
        for code, name, district in zip(codes, names, dists):
            if code:
                FACILITY_COORDS.setdefault(code, (None, None, name or code, district))


_MCH_PATTERN = 'Maternal|Child|Neonatal|Newborn'
_MCH_PROGRAMS = frozenset([
    'ANC PROGRAM', 'LABOUR AND DELIVERY PROGRAM', 'PNC PROGRAM',
    'NEONATAL PROGRAM', 'MATERNAL AND CHILD HEALTH',
])
_MNID_COLUMNS = [
    'person_id', 'encounter_id', 'Date', 'Program', 'Reporting_Program',
    'Service_Area', 'Facility', 'Facility_CODE', 'District', 'Encounter',
    'obs_value_coded', 'concept_name', 'Value', 'ValueN', 'new_revisit',
    'Home_district', 'TA', 'Village', 'Age', 'Age_Group', 'Gender',
    'Source_Program',
]


def prepare_mnid_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalise the live shared MAHIS dataframe used across MNID sections."""
    if df is None:
        return pd.DataFrame()

    source_attrs = dict(getattr(df, 'attrs', {}) or {})

    # Drop columns not used by MNID before the expensive normalization pass.
    keep = [c for c in _MNID_COLUMNS if c in df.columns]
    if keep:
        df = df[keep]

    # Filter down to MCH rows before normalizing, so _derive_person_level_context
    # runs on ~7k rows instead of 248k. Match on the exact program names rather than
    # a text pattern - 'Maternal|Child|Neonatal|Newborn' misses 'ANC PROGRAM',
    # 'LABOUR AND DELIVERY PROGRAM', etc.
    _pc = 'Program' if 'Program' in df.columns else ('Reporting_Program' if 'Reporting_Program' in df.columns else None)
    if _pc:
        _mch_mask = df[_pc].fillna('').str.upper().isin(_MCH_PROGRAMS)
        if _mch_mask.any():
            df = df[_mch_mask]

    if df.empty:
        empty = pd.DataFrame()
        empty.attrs.update(source_attrs)
        return empty

    mch_full = _normalize_mnid_semantics(df)
    program_col = 'Reporting_Program' if 'Reporting_Program' in mch_full.columns else 'Program'
    if program_col in mch_full.columns:
        mch_full = mch_full[
            mch_full[program_col].fillna('').str.contains(
                _MCH_PATTERN,
                case=False,
                na=False,
            )
        ]
    if 'Date' in mch_full.columns:
        mch_full['Date'] = pd.to_datetime(mch_full['Date'], errors='coerce')

    mch_full.attrs.update(source_attrs)
    register_facility_metadata(mch_full)
    return mch_full


def serialize_store_df(df: pd.DataFrame) -> list[dict]:
    """Convert dataframe rows to JSON-safe records for Dash stores."""
    if df is None or df.empty:
        return []
    safe_df = df.copy()

    def _json_safe_value(value):
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, dict):
            return json.dumps(value, default=str)
        if isinstance(value, (list, tuple, set)):
            return json.dumps(list(value), default=str)
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                pass
        return str(value)

    for column in safe_df.columns:
        if pd.api.types.is_datetime64_any_dtype(safe_df[column]):
            safe_df[column] = pd.to_datetime(safe_df[column], errors='coerce').apply(
                lambda item: item.isoformat() if pd.notna(item) else None
            )
        elif safe_df[column].dtype == "object":
            safe_df[column] = safe_df[column].map(_json_safe_value)

    return safe_df.to_dict(orient='records')


def deserialize_store_df(records: list[dict] | None) -> pd.DataFrame:
    """Rebuild a dataframe from a Dash store payload."""
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame.from_records(records)
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    register_facility_metadata(df)
    return df
