"""MNID dataframe preparation and serialization helpers."""

import json
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

_CONCEPT_ALIASES = {
    'VItamin K Given?': 'Vitamin K given',
    'Vitamin K given?': 'Vitamin K given',
    'Resuscitation method': 'Neonatal resuscitation provided',
    'Resuscitation Type': 'Neonatal resuscitation provided',
    'Type of resuscitation': 'Neonatal resuscitation provided',
    'Breast feeding in the first hour of birth': 'Breast feeding',
    'Gestation age to be used': 'Gestational age recorded',
    'Antenatal corticosteroids': 'Antenatal corticosteroids given',
}

_OBS_VALUE_ALIASES = {
    'Bag Valve Mask Ventilation (BVM)': 'Bag and mask',
    'Stimulation': 'Stimulation only',
    'Bacille camile-guerin vaccination': 'BCG',
    'ga by ultrasound': 'GA by ultrasound',
    'Ga by palpation': 'GA by palpation',
    'Caesarean Section': 'Caesarean section',
}


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

    service_area = out.apply(_derive_service_area, axis=1)
    if 'Service_Area' in out.columns:
        existing = out['Service_Area'].fillna('').astype(str).str.strip()
        out['Service_Area'] = existing.where(existing.ne(''), service_area)
    else:
        out['Service_Area'] = service_area

    reporting_program = _normalize_reporting_program(out['Service_Area'])
    if 'Reporting_Program' in out.columns:
        existing = out['Reporting_Program'].fillna('').astype(str).str.strip()
        out['Reporting_Program'] = existing.where(existing.ne(''), reporting_program)
    else:
        out['Reporting_Program'] = reporting_program

    if 'Encounter' in out.columns:
        out['Encounter_Source'] = out['Encounter']
        out['Encounter'] = out.apply(_normalize_encounter, axis=1)

    return out


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
