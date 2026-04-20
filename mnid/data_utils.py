"""MNID dataframe preparation and serialization helpers."""

import json
import re
import pandas as pd

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
    'ga by ultrasound': 'GA by ultrasound',
    'Ga by palpation': 'GA by palpation',
    'Caesarean Section': 'Caesarean section',
    'if within phototherapy level of bilirubin – phototherapy': 'Phototherapy',
}


def _derive_contextual_concepts(out: pd.DataFrame) -> pd.DataFrame:
    if out.empty or 'concept_name' not in out.columns:
        return out

    concept_series = out['concept_name'].fillna('').astype(str).str.strip()
    obs_series = out['obs_value_coded'].fillna('').astype(str).str.strip() if 'obs_value_coded' in out.columns else pd.Series('', index=out.index)
    val_series = out['Value'].fillna('').astype(str).str.strip() if 'Value' in out.columns else pd.Series('', index=out.index)
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


def _derive_person_level_context(out: pd.DataFrame) -> pd.DataFrame:
    if out.empty or 'person_id' not in out.columns:
        return out

    concept = out['concept_name'].fillna('').astype(str).str.strip() if 'concept_name' in out.columns else pd.Series('', index=out.index)
    obs = out['obs_value_coded'].fillna('').astype(str).str.strip() if 'obs_value_coded' in out.columns else pd.Series('', index=out.index)
    value = out['Value'].fillna('').astype(str).str.strip() if 'Value' in out.columns else pd.Series('', index=out.index)
    service = out['Service_Area'].fillna('').astype(str).str.strip() if 'Service_Area' in out.columns else pd.Series('', index=out.index)
    combined = obs.where(obs.ne(''), value)
    concept_lower = concept.str.lower()
    combined_lower = combined.str.lower()

    person_ctx = pd.DataFrame({'person_id': out['person_id'].dropna().astype(str).unique()})

    def _assign_flag(name: str, mask: pd.Series) -> None:
        if len(mask) != len(out):
            return
        people = out.loc[mask.fillna(False), 'person_id'].dropna().astype(str).unique().tolist()
        person_ctx[name] = person_ctx['person_id'].isin(people).map({True: 'Yes', False: ''})

    def _ctx_series(name: str) -> pd.Series:
        if name in person_ctx.columns:
            return person_ctx[name].fillna('').astype(str)
        return pd.Series('', index=person_ctx.index)

    anc_mask = service.eq('ANC')
    labour_mask = service.eq('Labour')
    pnc_mask = service.eq('PNC')
    newborn_mask = service.eq('Newborn')

    _assign_flag(
        'mnid_anc_hiv_test_done',
        anc_mask & (
            concept.isin(['HIV Test', 'HIV status', 'HIV Positive', 'Mother HIV Status', 'New HIV status'])
            | concept_lower.eq('hiv test')
            | concept_lower.str.contains('hiv', na=False)
        ) & ~combined_lower.isin(['', 'not done', 'unknown', 'negative', 'non-reactive']),
    )
    _assign_flag(
        'mnid_anc_hb_screened',
        anc_mask & (
            concept.isin(['Hb(g/dL)', 'Last HB result', 'Hemoglobin', 'Haemoglobin'])
            | concept_lower.str.contains('hb\\(g/dl\\)|hemoglobin|haemoglobin', regex=True, na=False)
        ) & ~combined_lower.isin(['', 'not done']),
    )
    _assign_flag(
        'mnid_anc_syphilis_tested',
        anc_mask & (
            concept.isin(['Syphilis Test Result', 'Mother VDRL/Syphilis result'])
            | concept_lower.str.contains('syphilis', na=False)
        ) & ~combined_lower.isin(['', 'not done', 'unknown']),
    )
    _assign_flag(
        'mnid_anc_mrdt_tested',
        anc_mask & (
            concept.isin(['mRDT results', 'Malaria Test Result', 'Malaria Parasites Result'])
            | concept_lower.str.contains('mrdt|malaria test result|malaria parasites result', regex=True, na=False)
        ) & ~combined_lower.isin(['', 'not done', 'unknown']),
    )
    _assign_flag(
        'mnid_anc_bp_screened',
        anc_mask & concept.isin(['Systolic blood pressure', 'Diastolic blood pressure', 'Systolic', 'Diastolic', 'Blood Pressure']),
    )

    _assign_flag(
        'mnid_labour_partograph_used',
        labour_mask & (
            (concept.isin(['Was a partograph used', 'Was a partograph used?']) & combined_lower.eq('yes'))
            | concept_lower.str.contains('partograph', na=False)
        ),
    )
    _assign_flag(
        'mnid_labour_preterm',
        labour_mask & (
            (concept.isin(['Obstetric complications']) & combined_lower.eq('preterm labour'))
            | concept_lower.str.contains('preterm labour', na=False)
        ),
    )
    _assign_flag(
        'mnid_labour_corticosteroids',
        labour_mask & (
            concept.isin(['Antenatal corticosteroids', 'Antenatal corticosteroids given', 'Corticosteroids'])
            | concept_lower.str.contains('corticosteroid', na=False)
        ) & combined_lower.ne(''),
    )
    _assign_flag(
        'mnid_labour_pph',
        labour_mask & (
            (concept.isin(['PPH']) & ~combined_lower.isin(['', 'no', 'negative']))
            | ((concept.isin(['Obstetric complications']) | concept_lower.str.contains('obstetric complication', na=False))
               & combined_lower.str.contains('post partum haemorrhage|pph', regex=True, na=False))
        ),
    )
    obstetric_care = labour_mask & (
        concept.isin(['Obstetric Care', 'Obstetric Care provided'])
        | concept_lower.str.contains('obstetric care', na=False)
    )
    _assign_flag('mnid_labour_pph_oxytocin', obstetric_care & combined_lower.eq('oxytocin'))
    _assign_flag('mnid_labour_pph_txa', obstetric_care & combined_lower.eq('tranexamic acid'))
    _assign_flag('mnid_labour_pph_misoprostol', obstetric_care & combined_lower.eq('misoprostol'))
    _assign_flag(
        'mnid_labour_azithromycin',
        labour_mask & (
            concept.isin(['Prophylactic azithromycin given'])
            | concept_lower.str.contains('azithromycin', na=False)
            | combined_lower.str.contains('azithromycin', na=False)
        ),
    )

    _assign_flag(
        'mnid_pnc_hiv_test_positive',
        pnc_mask & (
            (concept.eq('Mother HIV Status') & combined_lower.eq('positive'))
            | (concept.eq('New HIV status') & combined_lower.eq('positive'))
        ),
    )

    _assign_flag(
        'mnid_newborn_kmc',
        newborn_mask & (
            concept.isin(['iKMC initiated', 'Prematurity/Kangaroo', 'Management given to newborn'])
            | concept_lower.str.contains('kmc|kangaroo', regex=True, na=False)
            | combined_lower.str.contains('kangaroo mother care|continuous kmc|intermittent kmc|admit to kmc', regex=True, na=False)
        ),
    )
    _assign_flag(
        'mnid_newborn_cpap',
        newborn_mask & (
            concept.isin(['CPAP support'])
            | concept_lower.str.contains('cpap', na=False)
            | combined_lower.str.contains('cpap', na=False)
        ),
    )
    _assign_flag(
        'mnid_newborn_phototherapy',
        newborn_mask & (
            concept.isin(['Phototherapy given'])
            | concept_lower.str.contains('phototherapy', na=False)
            | combined_lower.str.contains('phototherapy', na=False)
        ),
    )
    _assign_flag(
        'mnid_newborn_jaundice',
        newborn_mask & (
            concept.isin(['Clinical jaundice'])
            | concept_lower.str.contains('jaundice', na=False)
            | combined_lower.str.contains('jaundice', na=False)
        ),
    )
    _assign_flag(
        'mnid_newborn_sepsis',
        newborn_mask & (
            concept.isin(['Neonatal Sepsis - Early Onset', 'Neonatal Sepsis - Late Onset'])
            | concept_lower.str.contains('sepsis', na=False)
        ),
    )
    _assign_flag(
        'mnid_newborn_parenteral_antibiotics',
        newborn_mask & (
            concept.isin(['Parenteral antibiotics given', 'Management given to newborn'])
            | concept_lower.str.contains('antibiotic', na=False)
            | combined_lower.str.contains('antibiotic', na=False)
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
    person_ctx['mnid_labour_preterm_corticosteroids'] = (
        _ctx_series('mnid_labour_preterm').eq('Yes')
        & _ctx_series('mnid_labour_corticosteroids').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_labour_pph_bundle_received'] = (
        _ctx_series('mnid_labour_pph').eq('Yes')
        & _ctx_series('mnid_labour_pph_bundle_proxy').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_newborn_jaundice_phototherapy'] = (
        _ctx_series('mnid_newborn_jaundice').eq('Yes')
        & _ctx_series('mnid_newborn_phototherapy').eq('Yes')
    ).map({True: 'Yes', False: ''})
    person_ctx['mnid_newborn_sepsis_antibiotics'] = (
        _ctx_series('mnid_newborn_sepsis').eq('Yes')
        & _ctx_series('mnid_newborn_parenteral_antibiotics').eq('Yes')
    ).map({True: 'Yes', False: ''})

    birth_weight_rows = out.loc[concept.eq('Birth weight'), ['person_id']].copy()
    value_numeric = out['ValueN'] if 'ValueN' in out.columns else pd.Series([None] * len(out), index=out.index)
    birth_weight_rows['mnid_birth_weight_g'] = [
        _first_numeric(pd.Series([vn, ov, vv]))
        for vn, ov, vv in zip(value_numeric.loc[birth_weight_rows.index], obs.loc[birth_weight_rows.index], value.loc[birth_weight_rows.index])
    ]
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

    person_ctx['person_id'] = person_ctx['person_id'].astype(str)
    merged = out.copy()
    merged['person_id'] = merged['person_id'].astype(str)
    return merged.merge(person_ctx, on='person_id', how='left')


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

    out = df.copy()
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

    service_area = out.apply(_derive_service_area, axis=1)
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
        out['Encounter'] = out.apply(_normalize_encounter, axis=1)

    return _derive_person_level_context(out)


def register_facility_metadata(df: pd.DataFrame) -> None:
    """Update live facility metadata caches from the current MNID dataframe."""
    if df is None or df.empty:
        return

    if {'Facility_CODE', 'Facility'}.issubset(df.columns):
        fac_meta = df[['Facility_CODE', 'Facility']].dropna().drop_duplicates()
        for row in fac_meta.itertuples(index=False):
            code = str(row.Facility_CODE).strip()
            name = str(row.Facility).strip()
            if code and name:
                FACILITY_NAMES[code] = name
                if code not in ALL_FACILITIES:
                    ALL_FACILITIES.append(code)

    if {'Facility_CODE', 'District'}.issubset(df.columns):
        dist_meta = df[['Facility_CODE', 'District']].dropna().drop_duplicates()
        for row in dist_meta.itertuples(index=False):
            code = str(row.Facility_CODE).strip()
            district = str(row.District).strip()
            if code and district:
                FACILITY_DISTRICT[code] = district
                if district not in ALL_DISTRICTS:
                    ALL_DISTRICTS.append(district)

    if {'Facility_CODE', 'Facility', 'District'}.issubset(df.columns):
        combo = df[['Facility_CODE', 'Facility', 'District']].dropna().drop_duplicates()
        for row in combo.itertuples(index=False):
            code = str(row.Facility_CODE).strip()
            name = str(row.Facility).strip()
            district = str(row.District).strip()
            if code:
                FACILITY_COORDS.setdefault(code, (None, None, name or code, district))


def prepare_mnid_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalise the live shared MAHIS dataframe used across MNID sections."""
    if df is None:
        return pd.DataFrame()

    source_attrs = dict(getattr(df, 'attrs', {}) or {})
    mch_full = _normalize_mnid_semantics(df)
    program_col = 'Reporting_Program' if 'Reporting_Program' in mch_full.columns else 'Program'
    if program_col in mch_full.columns:
        mch_full = mch_full[
            mch_full[program_col].fillna('').str.contains(
                'Maternal|Child|Neonatal|Newborn',
                case=False,
                na=False,
            )
        ].copy()
    if 'Date' in mch_full.columns:
        mch_full['Date'] = pd.to_datetime(mch_full['Date'], errors='coerce')

    mch_full.attrs.update(source_attrs)
    register_facility_metadata(mch_full)
    return mch_full


def serialize_store_df(df: pd.DataFrame) -> list[dict]:
    """Convert dataframe rows to JSON-safe records for Dash stores."""
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient='records', date_format='iso'))


def deserialize_store_df(records: list[dict] | None) -> pd.DataFrame:
    """Rebuild a dataframe from a Dash store payload."""
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame.from_records(records)
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    register_facility_metadata(df)
    return df
