"""MNID dataframe preparation and serialization helpers."""

import json
import pandas as pd

from .constants import FACILITY_DISTRICT, FACILITY_NAMES


def register_facility_metadata(df: pd.DataFrame) -> None:
    """Update facility name and district maps from live MNID data."""
    if df is None or df.empty:
        return

    if {'Facility_CODE', 'Facility'}.issubset(df.columns):
        fac_meta = df[['Facility_CODE', 'Facility']].dropna().drop_duplicates()
        for row in fac_meta.itertuples(index=False):
            code = str(row.Facility_CODE).strip()
            name = str(row.Facility).strip()
            if code and name:
                FACILITY_NAMES[code] = name

    if {'Facility_CODE', 'District'}.issubset(df.columns):
        dist_meta = df[['Facility_CODE', 'District']].dropna().drop_duplicates()
        for row in dist_meta.itertuples(index=False):
            code = str(row.Facility_CODE).strip()
            district = str(row.District).strip()
            if code and district:
                FACILITY_DISTRICT[code] = district


def prepare_mnid_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalise the MNID dataframe used across renderer sections."""
    if df is None:
        return pd.DataFrame()

    mch_full = df.copy()
    if 'Program' in mch_full.columns:
        mch_full = mch_full[
            mch_full['Program'].fillna('').str.contains('Maternal|Neonatal', case=False, na=False)
        ].copy()
    if 'Date' in mch_full.columns:
        mch_full['Date'] = pd.to_datetime(mch_full['Date'], errors='coerce')

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

