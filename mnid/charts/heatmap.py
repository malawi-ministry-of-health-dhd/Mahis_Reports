"""
MNID heatmap pre-computation and figure builders.

Contains vectorised coverage-matrix helpers, the heatmap store pre-computation,
facility performance heatmap, the Malawi geographic map, district treemap, and
the right-panel stat builder.
"""
import pandas as pd
import plotly.graph_objects as go
import logging
from dash import html, dcc

from mnid.core.constants import (
    OK_C, WARN_C, DANGER_C, INFO_C, MUTED, GRID_C, BG, BORDER, TEXT, DIM, FONT,
    HEATMAP_CS,
    FACILITY_DISTRICT as _FACILITY_DISTRICT,
    ALL_FACILITIES as _ALL_FACILITIES,
    ALL_DISTRICTS as _ALL_DISTRICTS,
    FACILITY_NAMES as _FACILITY_NAMES,
)
from mnid.charts.chart_helpers import _display_pct, _infer_facility_type, _contrast_text
from mnid.charts.geo_utils import (
    load_malawi_district_geojson as _load_malawi_district_geojson,
    build_geo_reference as _build_geo_reference,
    derive_facility_positions as _derive_facility_positions,
)

_LOGGER = logging.getLogger(__name__)


def _mask(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """Build boolean row mask from a filter config dict without calling create_count."""
    mask = pd.Series(True, index=df.index)
    for i in range(1, 11):
        var = cfg.get(f'variable{i}')
        val = cfg.get(f'value{i}')
        if not var or not val:
            break
        if var not in df.columns:
            return pd.Series(False, index=df.index)
        mask &= df[var].isin(val) if isinstance(val, list) else (df[var] == val)
    return mask


def _matrix_by_group(df: pd.DataFrame, inds: list,
                     group_col: str, groups: list) -> list:
    """
    Vectorized: one groupby per indicator (not one filter per group x indicator).
    Returns z[indicator_idx][group_idx] = coverage % or None.
    """
    n_by_grp = {}
    d_by_grp = {}
    for ind in inds:
        nm = _mask(df, ind['numerator_filters'])
        dm = _mask(df, ind['denominator_filters'])
        n_by_grp[ind['id']] = df[nm].groupby(group_col)['person_id'].nunique().to_dict()
        d_by_grp[ind['id']] = df[dm].groupby(group_col)['person_id'].nunique().to_dict()

    z = []
    for ind in inds:
        row = []
        for g in groups:
            n = n_by_grp[ind['id']].get(g, 0)
            d = d_by_grp[ind['id']].get(g, 0)
            row.append(round(n / d * 100, 1) if d > 0 else None)
        z.append(row)
    return z


def _matrix_monthly(df: pd.DataFrame, inds: list) -> tuple:
    """Monthly view for a single facility. Returns (x_labels, z)."""
    d2 = df
    d2['_m'] = pd.to_datetime(d2['Date']).dt.to_period('M')
    periods = sorted(d2['_m'].dropna().unique())
    if not periods:
        return [], []

    x_labels = [f"{p.strftime('%b')} {str(p.year)[2:]}" for p in periods]
    n_by_m = {}
    d_by_m = {}
    for ind in inds:
        nm = _mask(d2, ind['numerator_filters'])
        dm = _mask(d2, ind['denominator_filters'])
        n_by_m[ind['id']] = d2[nm].groupby('_m')['person_id'].nunique().to_dict()
        d_by_m[ind['id']] = d2[dm].groupby('_m')['person_id'].nunique().to_dict()

    z = []
    for ind in inds:
        row = []
        for p in periods:
            n = n_by_m[ind['id']].get(p, 0)
            d = d_by_m[ind['id']].get(p, 0)
            row.append(round(n / d * 100, 1) if d > 0 else None)
        z.append(row)
    return x_labels, z


def _cov_color(pct):
    if pct is None: return '#E2E8F0'
    try:
        v = float(pct)
    except (TypeError, ValueError):
        return '#E2E8F0'
    if v != v: return '#E2E8F0'  # NaN → no-data grey
    if v >= 80: return OK_C      # green  — on target
    if v >= 60: return WARN_C    # yellow — 60–79
    return DANGER_C              # red    — below 60


# # MNID vectorized facility coverage computation

# MNID heatmap pre-computation

def _compute_heatmap_store(mch_full: pd.DataFrame, tracked: list,
                           facility_code: str) -> dict:
    """Pre-compute all view x year matrices into a JSON-serialisable store."""
    current_district = _FACILITY_DISTRICT.get(facility_code, '')
    if len(mch_full) and 'Facility_CODE' in mch_full.columns:
        all_facilities = sorted(mch_full['Facility_CODE'].dropna().astype(str).unique().tolist())
    else:
        all_facilities = sorted(_ALL_FACILITIES[:])

    geojson = _load_malawi_district_geojson()
    geo_districts = sorted({
        f.get('properties', {}).get('shapeName')
        for f in (geojson or {}).get('features', [])
        if f.get('properties', {}).get('shapeName')
    })
    if len(mch_full) and 'District' in mch_full.columns:
        data_districts = sorted(mch_full['District'].dropna().astype(str).unique().tolist())
    else:
        data_districts = sorted({
            _FACILITY_DISTRICT.get(f, '')
            for f in all_facilities
            if _FACILITY_DISTRICT.get(f)
        })
    all_districts = sorted(set(data_districts) | set(geo_districts) | set(_ALL_DISTRICTS))

    if facility_code and facility_code not in all_facilities:
        all_facilities.insert(0, facility_code)
    if current_district and current_district not in all_districts:
        all_districts.insert(0, current_district)

    sorted_inds = []
    for cat in ['ANC', 'Labour', 'Newborn', 'PNC']:
        sorted_inds.extend(i for i in tracked if i.get('category') == cat)
    sorted_inds.extend(i for i in tracked if i not in sorted_inds)

    y_labels  = [i['label'][:32] for i in sorted_inds]
    y_targets = [i['target']     for i in sorted_inds]

    store = {
        'y_labels': y_labels, 'y_targets': y_targets,
        'current_fac': facility_code, 'current_district': current_district,
        'all_facilities': all_facilities, 'all_districts': all_districts,
        'monthly': {}, 'by_facility': {}, 'by_district': {},
        'by_district_facs': {d: {} for d in all_districts},
        'yearly': {}, 'district_avgs': {},
    }

    if not len(mch_full) or not sorted_inds:
        return store

    years = []
    if 'Date' in mch_full.columns:
        years = sorted(mch_full['Date'].dt.year.dropna().astype(int).unique().tolist())
    year_options = {'All years': None, **{str(y): y for y in years}}
    district_facs_map = {
        d: [f for f in all_facilities if _FACILITY_DISTRICT.get(f) == d]
        for d in all_districts
    }
    store['facilities_by_district'] = district_facs_map

    for ylbl, yval in year_options.items():
        df = mch_full[mch_full['Date'].dt.year == yval] if yval else mch_full
        if not len(df):
            for key in ['monthly', 'by_facility', 'by_district']:
                store[key][ylbl] = {'x': [], 'z': [], 'tick_angle': 0}
            for d in all_districts:
                store['by_district_facs'][d][ylbl] = {'x': [], 'z': [], 'tick_angle': -30}
            store['district_avgs'][ylbl] = {d: None for d in all_districts}
            continue

        # Monthly - current facility only
        fac_df = df[df['Facility_CODE'] == facility_code]
        if len(fac_df):
            x_m, z_m = _matrix_monthly(fac_df, sorted_inds)
        else:
            x_m, z_m = [], []
        store['monthly'][ylbl] = {'x': x_m, 'z': z_m, 'tick_angle': 0}

        # Vectorised groupby for facility and district - one pass per indicator
        n_by_fac  = {}; d_by_fac  = {}
        n_by_dist = {}; d_by_dist = {}
        has_dist  = 'District' in df.columns

        for ind in sorted_inds:
            nm = _mask(df, ind['numerator_filters'])
            dm = _mask(df, ind['denominator_filters'])
            n_by_fac[ind['id']]  = df[nm].groupby('Facility_CODE')['person_id'].nunique().to_dict()
            d_by_fac[ind['id']]  = df[dm].groupby('Facility_CODE')['person_id'].nunique().to_dict()
            if has_dist:
                n_by_dist[ind['id']] = df[nm].groupby('District')['person_id'].nunique().to_dict()
                d_by_dist[ind['id']] = df[dm].groupby('District')['person_id'].nunique().to_dict()

        def _cell(n_dict, d_dict, ind_id, key):
            n = n_dict.get(ind_id, {}).get(key, 0)
            d = d_dict.get(ind_id, {}).get(key, 0)
            return round(n / d * 100, 1) if d > 0 else None

        # All facilities
        x_f = [f'{f}*' if f == facility_code else f for f in all_facilities]
        z_f = [[_cell(n_by_fac, d_by_fac, ind['id'], fac) for fac in all_facilities]
               for ind in sorted_inds]
        store['by_facility'][ylbl] = {
            'x': x_f, 'z': z_f, 'tick_angle': -30,
            'districts': [_FACILITY_DISTRICT.get(f, '') for f in all_facilities],
        }

        # All districts
        if has_dist:
            data_districts = sorted(df['District'].dropna().unique().tolist())
            z_d = [[_cell(n_by_dist, d_by_dist, ind['id'], dist) for dist in data_districts]
                   for ind in sorted_inds]
            store['by_district'][ylbl] = {'x': data_districts[:], 'z': z_d, 'tick_angle': -20}
            d_avgs = {}
            for di, dist in enumerate(data_districts):
                vals = [
                    z_d[ii][di] for ii in range(len(sorted_inds))
                    if (ii < len(z_d) and di < len(z_d[ii])
                        and z_d[ii][di] is not None
                        and z_d[ii][di] == z_d[ii][di])
                ]
                d_avgs[dist] = round(sum(vals) / len(vals), 1) if vals else None
            store['district_avgs'][ylbl] = d_avgs
        else:
            store['by_district'][ylbl]   = {'x': [], 'z': [], 'tick_angle': -20}
            store['district_avgs'][ylbl] = {}

        # Per-district facility breakdowns
        for dist in all_districts:
            dfacs = district_facs_map[dist]
            x_df  = [f'{f}*' if f == facility_code else f for f in dfacs]
            z_df  = [[_cell(n_by_fac, d_by_fac, ind['id'], fac) for fac in dfacs]
                     for ind in sorted_inds]
            store['by_district_facs'][dist][ylbl] = {'x': x_df, 'z': z_df, 'tick_angle': -30}

    # Year-over-year for current facility
    fac_full = mch_full[mch_full['Facility_CODE'] == facility_code]
    if len(fac_full) and 'Date' in fac_full.columns:
        years = sorted(fac_full['Date'].dt.year.dropna().astype(int).unique().tolist())
        n_yr = {}; d_yr = {}
        for ind in sorted_inds:
            nm = _mask(fac_full, ind['numerator_filters'])
            dm = _mask(fac_full, ind['denominator_filters'])
            yr_col = fac_full['Date'].dt.year.astype(int)
            n_yr[ind['id']] = fac_full[nm].groupby(yr_col)['person_id'].nunique().to_dict()
            d_yr[ind['id']] = fac_full[dm].groupby(yr_col)['person_id'].nunique().to_dict()
        x_yr = [str(y) for y in years]
        z_yr  = [[round(n_yr[ind['id']].get(yr, 0) / d_yr[ind['id']].get(yr, 0) * 100, 1)
                  if d_yr[ind['id']].get(yr, 0) > 0 else None
                  for yr in years] for ind in sorted_inds]
        store['yearly'] = {'x': x_yr, 'z': z_yr, 'tick_angle': 0}

    # # MNID encounter volume counts for the right panel
    counts: dict = {}
    if 'Encounter' in mch_full.columns:
        enc_col = mch_full['Encounter'].fillna('').str.upper()
        fac_mask = mch_full['Facility_CODE'] == facility_code
        for ylbl, yval in {'All years': None, '2025': 2025, '2026': 2026}.items():
            if yval and 'Date' in mch_full.columns:
                yr_mask = mch_full['Date'].dt.year == yval
            else:
                yr_mask = pd.Series(True, index=mch_full.index)
            df_yr = mch_full[yr_mask & fac_mask]
            enc_yr = df_yr['Encounter'].fillna('').str.upper() if len(df_yr) else pd.Series(dtype=str)
            counts[ylbl] = {
                'ANC visits':   int(df_yr[enc_yr.str.contains('ANC',      na=False)]['person_id'].nunique()),
                'Deliveries':   int(df_yr[enc_yr.str.contains('LABOUR|DELIVERY|BIRTH', na=False)]['person_id'].nunique()),
                'PNC visits':   int(df_yr[enc_yr.str.contains('PNC|POSTNATAL|POST.NATAL', na=False)]['person_id'].nunique()),
                'All MCH encounters': int(df_yr['person_id'].nunique()),
            }
    store['counts'] = counts

    return store


def _compute_heatmap_store_from_agg(
    agg_df: pd.DataFrame,
    tracked: list,
    facility_code: str,
) -> dict:
    """Build the heatmap store from pre-aggregated data instead of raw row scans.

    Replaces _compute_heatmap_store when the aggregate parquet is available,
    converting seconds of groupby work into millisecond pandas filter+pivot ops.
    The 'counts' key is returned empty since encounter-type counts are not in the
    aggregate.
    """
    current_district = _FACILITY_DISTRICT.get(facility_code, '')

    ind_ids = {i['id'] for i in tracked}
    base = agg_df[agg_df['indicator_id'].isin(ind_ids) & (agg_df['grain'] == 'monthly')].copy()

    agg_facs  = sorted(base['facility_code'].dropna().astype(str).unique().tolist())
    agg_dists = sorted(base['district'].dropna().astype(str).unique().tolist())

    all_facilities = sorted(set(agg_facs) | set(_ALL_FACILITIES))
    all_districts  = sorted(set(agg_dists) | set(_ALL_DISTRICTS))

    geojson = _load_malawi_district_geojson()
    geo_districts = sorted({
        f.get('properties', {}).get('shapeName')
        for f in (geojson or {}).get('features', [])
        if f.get('properties', {}).get('shapeName')
    })
    all_districts = sorted(set(all_districts) | set(geo_districts))

    if facility_code and str(facility_code) not in all_facilities:
        all_facilities.insert(0, str(facility_code))
    if current_district and current_district not in all_districts:
        all_districts.insert(0, current_district)

    sorted_inds = []
    for cat in ['ANC', 'Labour', 'Newborn', 'PNC']:
        sorted_inds.extend(i for i in tracked if i.get('category') == cat)
    sorted_inds.extend(i for i in tracked if i not in sorted_inds)

    y_labels  = [i['label'][:32] for i in sorted_inds]
    y_targets = [i['target']     for i in sorted_inds]

    district_facs_map = {
        d: [f for f in all_facilities if _FACILITY_DISTRICT.get(f) == d]
        for d in all_districts
    }

    store = {
        'y_labels': y_labels, 'y_targets': y_targets,
        'current_fac': facility_code, 'current_district': current_district,
        'all_facilities': all_facilities, 'all_districts': all_districts,
        'facilities_by_district': district_facs_map,
        'monthly': {}, 'by_facility': {}, 'by_district': {},
        'by_district_facs': {d: {} for d in all_districts},
        'yearly': {}, 'district_avgs': {},
        'counts': {},
    }

    if base.empty or not sorted_inds:
        return store

    base['_yr'] = base['period_start'].dt.year
    years = sorted(base['_yr'].dropna().astype(int).unique().tolist())
    year_options = {'All years': None, **{str(y): y for y in years}}
    ind_order = [i['id'] for i in sorted_inds]

    def _pct_dict(sub, group_col):
        """Return {ind_id: {group_key: float|None}} with NaN explicitly replaced by None."""
        if sub.empty:
            return {}
        g = sub.groupby(['indicator_id', group_col])[['numerator', 'denominator']].sum().reset_index()
        g['pct'] = (g['numerator'] / g['denominator'].where(g['denominator'] > 0) * 100).round(1)
        piv = g.pivot(index='indicator_id', columns=group_col, values='pct')
        # Convert NaN → None so _cov_color / _display_pct treat them as "no data"
        result = {}
        for iid in piv.index:
            row = {}
            for col in piv.columns:
                val = piv.at[iid, col]
                row[col] = None if (val != val) else float(val)  # NaN != NaN
            result[iid] = row
        return result

    def _z_matrix(pct_d, keys):
        """Build z[indicator_idx][key_idx] from a pct dict-of-dicts."""
        return [[pct_d.get(iid, {}).get(k) for k in keys] for iid in ind_order]

    for ylbl, yval in year_options.items():
        sub = base[base['_yr'] == yval] if yval else base

        if sub.empty:
            for key in ['monthly', 'by_facility', 'by_district']:
                store[key][ylbl] = {'x': [], 'z': [], 'tick_angle': 0}
            for d in all_districts:
                store['by_district_facs'][d][ylbl] = {'x': [], 'z': [], 'tick_angle': -30}
            store['district_avgs'][ylbl] = {d: None for d in all_districts}
            continue

        # monthly view: current facility only, pivot over period_start
        fac_sub = sub[sub['facility_code'] == str(facility_code)]
        if not fac_sub.empty:
            gm = fac_sub.groupby(['indicator_id', 'period_start'])[['numerator', 'denominator']].sum().reset_index()
            gm['pct'] = (gm['numerator'] / gm['denominator'].where(gm['denominator'] > 0) * 100).round(1)
            piv_m = gm.pivot(index='indicator_id', columns='period_start', values='pct')
            periods = sorted(piv_m.columns.tolist())
            x_m = [f"{pd.Timestamp(p).strftime('%b')} {str(pd.Timestamp(p).year)[2:]}" for p in periods]
            m_dict = piv_m.where(pd.notna, other=None).to_dict(orient='index')
            z_m = [[m_dict.get(iid, {}).get(p) for p in periods] for iid in ind_order]
        else:
            x_m, z_m = [], []
        store['monthly'][ylbl] = {'x': x_m, 'z': z_m, 'tick_angle': 0}

        # by facility, pivot over facility_code
        fp = _pct_dict(sub, 'facility_code')
        x_f = [f'{f}*' if f == str(facility_code) else f for f in all_facilities]
        z_f = _z_matrix(fp, all_facilities)
        store['by_facility'][ylbl] = {
            'x': x_f, 'z': z_f, 'tick_angle': -30,
            'districts': [_FACILITY_DISTRICT.get(f, '') for f in all_facilities],
        }

        # by district, pivot over district
        data_dists = sorted(sub['district'].dropna().astype(str).unique().tolist())
        if data_dists:
            dp = _pct_dict(sub, 'district')
            z_d = _z_matrix(dp, data_dists)
            d_avgs = {}
            for di, dist in enumerate(data_dists):
                vals = [
                    z_d[ii][di] for ii in range(len(sorted_inds))
                    if (ii < len(z_d) and di < len(z_d[ii])
                        and z_d[ii][di] is not None
                        and z_d[ii][di] == z_d[ii][di])  # exclude NaN (NaN != NaN)
                ]
                d_avgs[dist] = round(sum(vals) / len(vals), 1) if vals else None
            store['by_district'][ylbl] = {'x': data_dists, 'z': z_d, 'tick_angle': -20}
            store['district_avgs'][ylbl] = d_avgs
        else:
            store['by_district'][ylbl] = {'x': [], 'z': [], 'tick_angle': -20}
            store['district_avgs'][ylbl] = {}

        # per-district facility breakdowns, reuse fp computed above
        for dist in all_districts:
            dfacs = district_facs_map[dist]
            x_df = [f'{f}*' if f == str(facility_code) else f for f in dfacs]
            z_df = _z_matrix(fp, dfacs)
            store['by_district_facs'][dist][ylbl] = {'x': x_df, 'z': z_df, 'tick_angle': -30}

    # yearly view: current facility, year-over-year, pivot over _yr
    fac_all = base[base['facility_code'] == str(facility_code)]
    if not fac_all.empty and years:
        gy = fac_all.groupby(['indicator_id', '_yr'])[['numerator', 'denominator']].sum().reset_index()
        gy['pct'] = (gy['numerator'] / gy['denominator'].where(gy['denominator'] > 0) * 100).round(1)
        piv_yr = gy.pivot(index='indicator_id', columns='_yr', values='pct')
        yr_dict = piv_yr.where(pd.notna, other=None).to_dict(orient='index')
        store['yearly'] = {
            'x': [str(y) for y in years],
            'z': [[yr_dict.get(iid, {}).get(y) for y in years] for iid in ind_order],
            'tick_angle': 0,
        }

    return store


def _filter_by_fac_data(stored: dict, year: str, district=None):
    """Return (fac_keys, z_raw) from by_facility, filtered by district(s) if given."""
    by_fac = stored.get('by_facility', {}).get(year, {})
    all_x = by_fac.get('x', [])
    all_z = by_fac.get('z', [])
    fac_dists = by_fac.get('districts', [])

    if isinstance(district, list):
        focus = {d for d in district if d and d != 'All'}
    elif district and district != 'All':
        focus = {district}
    else:
        focus = set()

    if not focus:
        return all_x, all_z

    keep = [i for i, d in enumerate(fac_dists) if d in focus]
    fac_keys = [all_x[i] for i in keep]
    z_filtered = [[row[i] if i < len(row) else None for i in keep] for row in all_z]
    return fac_keys, z_filtered


def _build_facility_performance_heatmap_fig(stored: dict, year: str,
                                            district=None,
                                            sel_inds: list | None = None,
                                            facility_type: str | None = None) -> html.Div:
    """Facility-first display: all facilities if no district is selected,
    otherwise just the facilities within the selected district(s)."""
    all_labels = stored.get('y_labels', [])
    if sel_inds:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in sel_inds]
    else:
        rows_idx = list(range(len(all_labels)))

    # Determine which districts are actively selected
    if isinstance(district, list):
        focus_districts = [d for d in district if d and d != 'All']
    elif district and district != 'All':
        focus_districts = [district]
    else:
        focus_districts = []

    row_keys, z_raw = _filter_by_fac_data(stored, year, focus_districts)
    row_label = 'Facility'

    def _row_name(key):
        code = str(key or '').rstrip('*')
        return _FACILITY_NAMES.get(code, code)

    def _is_current(key):
        return str(key or '').rstrip('*') == str(stored.get('current_fac', ''))

    def _kind(key):
        return _infer_facility_type(str(key or '').rstrip('*'))

    selected_type = facility_type or 'All'
    table_rows = []
    for col_idx, row_key in enumerate(row_keys):
        kind = _kind(row_key)
        if selected_type != 'All' and kind != selected_type:
            continue
        row_vals = [
            _display_pct(z_raw[row_idx][col_idx])
            if row_idx < len(z_raw) and col_idx < len(z_raw[row_idx]) and z_raw[row_idx][col_idx] is not None
            else None
            for row_idx in rows_idx
        ]
        vals = [v for v in row_vals if v is not None]
        avg = round(sum(vals) / len(vals), 1) if vals else None
        table_rows.append({
            'name': _row_name(row_key),
            'avg': avg,
            'values': row_vals,
            'is_current': _is_current(row_key),
        })

    table_rows = [r for r in table_rows if any(v is not None for v in r['values'])]
    table_rows.sort(key=lambda r: (r['avg'] is None, -(r['avg'] or 0), r['name']))

    if not table_rows or not rows_idx:
        return html.Div(
            'No comparison data for this selection.',
            className='mnid-performance-table-empty',
        )

    def _header_cells(label: str) -> list:
        words = str(label or '').split()
        if not words:
            return ['-']
        lines = []
        current = words[0]
        for word in words[1:]:
            if len(current) + len(word) + 1 <= 16 and len(lines) < 2:
                current = f'{current} {word}'
            else:
                lines.append(current)
                current = word
                if len(lines) >= 2:
                    break
        remaining_words = words[len(' '.join(lines + [current]).split()):]
        if remaining_words:
            current = f"{current} {' '.join(remaining_words)}".strip()
        lines.append(current)
        if len(lines[-1]) > 16:
            lines[-1] = f"{lines[-1][:15].rstrip()}..."
        children = []
        for idx, line in enumerate(lines[:3]):
            if idx:
                children.append(html.Br())
            children.append(line)
        return children

    header_row = html.Tr([
        html.Th(row_label, className='mnid-performance-th mnid-performance-th-facility')
    ] + [
        html.Th(_header_cells(all_labels[i]), className='mnid-performance-th')
        for i in rows_idx
    ])

    body_rows = []
    for row in table_rows:
        name = f"{row['name']} *" if row['is_current'] else row['name']
        cells = [html.Td(name, className='mnid-performance-facility-cell')]
        for val in row['values']:
            bg = '#E2E8F0' if val is None else _cov_color(val)
            fg = '#475569' if val is None else _contrast_text(bg)
            txt = '-' if val is None else f'{val:.0f}%'
            cells.append(html.Td(txt, className='mnid-performance-value-cell', style={
                'backgroundColor': bg,
                'color': fg,
            }))
        body_rows.append(html.Tr(cells))

    return html.Div(className='mnid-performance-table-wrap', children=[
        html.Table(className='mnid-performance-matrix', children=[
            html.Thead(header_row),
            html.Tbody(body_rows),
        ])
    ])


def _build_performance_attention_table(stored: dict, year: str,
                                       district=None,
                                       facility_type: str | None = None,
                                       sel_inds: list | None = None) -> html.Div:
    """
    Shows the worst performers.
    Always facility-based, optionally filtered to selected district(s).
    """
    all_labels = stored.get('y_labels', [])
    all_targets = stored.get('y_targets', [])
    if sel_inds:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in sel_inds]
    else:
        rows_idx = list(range(len(all_labels)))

    if isinstance(district, list):
        focus_districts = [d for d in district if d and d != 'All']
    elif district and district != 'All':
        focus_districts = [district]
    else:
        focus_districts = []

    row_keys, z_raw = _filter_by_fac_data(stored, year, focus_districts)
    def _name(key):
        code = str(key or '').rstrip('*')
        return _FACILITY_NAMES.get(code, code)
    def _dist(key):
        return _FACILITY_DISTRICT.get(str(key or '').rstrip('*'), '')
    def _ftype(key):
        return _infer_facility_type(str(key or '').rstrip('*'))
    label_col = 'Facility'

    selected_type = facility_type or 'All'
    rows = []
    for col_idx, row_key in enumerate(row_keys):
        if selected_type != 'All' and _ftype(row_key) != selected_type:
            continue
        if str(row_key or '').rstrip('*') == str(stored.get('current_fac', '')):
            continue

        values = []
        critical = []
        for row_idx in rows_idx:
            if row_idx >= len(z_raw) or col_idx >= len(z_raw[row_idx]):
                continue
            val = z_raw[row_idx][col_idx]
            if val is None:
                continue
            pct = _display_pct(val)
            values.append(pct)
            tgt = all_targets[row_idx] if row_idx < len(all_targets) else 80
            if pct < tgt:
                critical.append((all_labels[row_idx], pct, tgt))

        if not values or not critical:
            continue

        critical.sort(key=lambda item: item[1])
        worst_pct = critical[0][1]
        worst_gap = min(item[1] - item[2] for item in critical)
        avg = round(sum(values) / len(values), 1)
        rows.append({
            'name': _name(row_key),
            'district': _dist(row_key),
            'type': _ftype(row_key),
            'avg': avg,
            'critical': [(label, pct) for label, pct, _ in critical[:2]],
            'critical_count': len(critical),
            'worst_pct': worst_pct,
            'worst_gap': worst_gap,
        })

    rows.sort(key=lambda row: (row['worst_pct'], row['worst_gap'], -row['critical_count'], row['avg'], row['name']))
    rows = rows[:5]

    second_col = 'District'
    third_col  = 'Facility Type'
    header = html.Tr([
        html.Th('#', className='mnid-attention-th mnid-attention-rank'),
        html.Th(label_col, className='mnid-attention-th'),
        html.Th(second_col, className='mnid-attention-th'),
        html.Th(third_col, className='mnid-attention-th'),
        html.Th('Critical Indicator(s)', className='mnid-attention-th'),
        html.Th('Average Performance', className='mnid-attention-th'),
    ])

    if not rows:
        return html.Div(className='mnid-performance-attention-wrap mnid-performance-attention-empty', children=[
            html.Div('FACILITIES REQUIRING ATTENTION', className='mnid-attention-title'),
            html.Div(
                'No facility attention data for this selection.',
                className='mnid-attention-empty-message',
            ),
        ])

    body = []
    for idx, row in enumerate(rows, start=1):
        if row['critical']:
            critical_children = []
            for pos, (label, pct) in enumerate(row['critical']):
                if pos:
                    critical_children.append(html.Br())
                critical_children.append(f'{label} ({pct:.0f}%)')
            critical_cell = html.Div(className='mnid-attention-critical', children=critical_children)
        else:
            critical_cell = html.Span('Monitoring', className='mnid-attention-monitoring')

        avg_color = _cov_color(row['avg'])
        extra_cells = [
            html.Td(row['district'],  className='mnid-attention-td'),
            html.Td(row['type'],      className='mnid-attention-td'),
        ]
        body.append(html.Tr([
            html.Td(str(idx), className='mnid-attention-td mnid-attention-rank'),
            html.Td(row['name'], className='mnid-attention-td mnid-attention-facility'),
            *extra_cells,
            html.Td(critical_cell, className='mnid-attention-td mnid-attention-critical-cell'),
            html.Td(
                html.Span(f'{row["avg"]:.0f}% (Avg)', style={'color': avg_color}),
                className='mnid-attention-td mnid-attention-avg',
                style={'backgroundColor': '#FFF7ED' if row['avg'] < 65 else ('#FFFBEB' if row['avg'] < 80 else '#F0FDF4')},
            ),
        ]))

    title = 'FACILITIES REQUIRING ATTENTION'
    return html.Div(className='mnid-performance-attention-wrap', children=[
        html.Div(title, className='mnid-attention-title'),
        html.Table(className='mnid-attention-table', children=[
            html.Thead(header),
            html.Tbody(body),
        ]),
    ])


# MNID heatmap figure builder

def _build_heatmap_fig(stored: dict, view: str, year: str,
                       district: str | None = None,
                       sel_inds: list | None = None) -> go.Figure:
    map_view = view if view in ('by_district', 'district_facs') else 'by_district'
    return _build_geo_heatmap_fig(stored, map_view, year, district, sel_inds)


# # MNID geographic map data for the main heatmap

def _build_geo_heatmap_fig(stored: dict, view: str, year: str,
                           district: str | None = None,
                           sel_inds: list | None = None) -> go.Figure:
    district_avgs = stored.get('district_avgs', {}).get(year, {})
    current_fac   = stored.get('current_fac', '')
    current_dist  = stored.get('current_district', '')
    all_labels    = stored.get('y_labels', [])
    dyn_districts = stored.get('all_districts', [])

    selected_labels = sel_inds if isinstance(sel_inds, list) else ([sel_inds] if sel_inds else [])
    if selected_labels:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in selected_labels]
    else:
        rows_idx = list(range(len(all_labels)))

    by_fac_data = stored.get('by_facility', {}).get(year, {})
    store_fac_x = by_fac_data.get('x', [])
    store_facs  = [f.rstrip('*') for f in store_fac_x]

    def _fac_avg(fac_code):
        fac_z = by_fac_data.get('z', [])
        key = f'{fac_code}*' if fac_code == current_fac else fac_code
        if key not in store_fac_x:
            return None
        ci = store_fac_x.index(key)
        vals = [fac_z[r][ci] for r in rows_idx
                if r < len(fac_z) and ci < len(fac_z[r])
                and fac_z[r][ci] is not None and fac_z[r][ci] == fac_z[r][ci]]  # exclude NaN
        return round(sum(vals) / len(vals), 1) if vals else None

    selected_dist = district if district not in (None, '', 'All') else None
    focus_dist  = selected_dist or current_dist
    geojson = _load_malawi_district_geojson()
    geo_ref = _build_geo_reference(geojson)
    if not geo_ref:
        fig = go.Figure()
        fig.add_annotation(text='District GeoJSON not available for MNID map',
                           xref='paper', yref='paper', x=0.5, y=0.5,
                           showarrow=False, font=dict(size=12, color=MUTED))
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, height=680)
        return fig

    district_rings = geo_ref.get('district_rings', {})
    district_centroids = geo_ref.get('district_centroids', {})
    y_scale = geo_ref.get('y_scale', 1.0)
    display_districts = sorted(set(dyn_districts) | set(district_rings.keys()) | set(district_avgs.keys()))

    fig = go.Figure()
    shapes = []
    hover_x = []
    hover_y = []
    hover_cd = []
    label_x = []
    label_y = []
    label_text = []

    for dist in display_districts:
        rings = district_rings.get(dist, [])
        if not rings:
            continue
        cov = district_avgs.get(dist)
        fill = _cov_color(cov) if cov is not None else '#E2E8F0'
        is_focus = (view == 'district_facs' and dist == focus_dist) or (view == 'by_district' and dist == selected_dist)
        line_color = '#0F172A' if is_focus else '#FFFFFF'
        line_width = 2.8 if is_focus else 1.4
        for pts in rings:
            path_str = 'M ' + ' L '.join(f'{x:.6f},{y:.6f}' for x, y in pts) + ' Z'
            shapes.append(dict(
                type='path', path=path_str, xref='x', yref='y',
                fillcolor=fill, line=dict(color=line_color, width=line_width), layer='below',
            ))
        cx, cy = district_centroids.get(dist, (None, None))
        if cx is not None and cy is not None:
            hover_x.append(cx)
            hover_y.append(cy)
            hover_cd.append([dist, f'{_display_pct(cov):.1f}%' if cov is not None else 'No data'])
            if view != 'by_facility':
                label_x.append(cx)
                label_y.append(cy)
                label_text.append(f'<b>{dist}</b><br>{_display_pct(cov):.1f}%' if cov is not None else f'<b>{dist}</b><br>No data')

    if shapes:
        fig.update_layout(shapes=shapes)

    if hover_x:
        fig.add_trace(go.Scatter(
            x=hover_x, y=hover_y, mode='markers',
            marker=dict(size=10, color='rgba(0,0,0,0)'),
            customdata=hover_cd,
            hovertemplate='<b>%{customdata[0]}</b><br>Avg coverage: %{customdata[1]}<extra></extra>',
            showlegend=False,
        ))

    if label_x:
        fig.add_trace(go.Scatter(
            x=label_x, y=label_y, mode='text', text=label_text,
            textfont=dict(size=10, color='#FFFFFF', family=FONT),
            hoverinfo='skip', showlegend=False,
        ))

    if view in ('by_facility', 'district_facs'):
        if view == 'by_facility':
            fac_codes = store_facs
        else:
            fac_codes = [f for f in store_facs if _FACILITY_DISTRICT.get(f) == focus_dist]
        facilities_by_district = stored.get('facilities_by_district', {})
        fac_positions = _derive_facility_positions(facilities_by_district, district_centroids)

        fac_x = []
        fac_y = []
        fac_text = []
        fac_size = []
        fac_color = []
        fac_text_pos = []
        for fac in fac_codes:
            pos = fac_positions.get(fac)
            if not pos:
                continue
            x, y = pos
            avg = _fac_avg(fac)
            name = _FACILITY_NAMES.get(fac, fac)
            dist = _FACILITY_DISTRICT.get(fac, '')
            fac_x.append(x)
            fac_y.append(y)
            fac_text.append(f'<b>{name}</b><br>{dist}<br>Avg coverage: {f"{_display_pct(avg):.1f}%" if avg is not None else "No data"}')
            fac_size.append(14 if fac == current_fac else 10)
            fac_color.append(_cov_color(avg) if avg is not None else '#CBD5E1')
            fac_text_pos.append('middle left' if x > 0.55 else 'middle right')

        if fac_x:
            fig.add_trace(go.Scatter(
                x=fac_x, y=fac_y, mode='markers+text',
                text=[_FACILITY_NAMES.get(f, f) for f in fac_codes if fac_positions.get(f)],
                textposition=fac_text_pos,
                textfont=dict(size=9, color=TEXT, family=FONT),
                hovertext=fac_text, hovertemplate='%{hovertext}<extra></extra>',
                marker=dict(size=fac_size, color=fac_color, line=dict(color='#FFFFFF', width=1.2), opacity=0.95),
                showlegend=False,
            ))

    x_range = [-0.02, 1.02]
    y_range = [-0.02, y_scale + 0.02]
    if view == 'district_facs' or (view == 'by_district' and selected_dist):
        zoom_dist = focus_dist if view == 'district_facs' else selected_dist
        focus_points = []
        for pts in district_rings.get(zoom_dist, []):
            focus_points.extend(pts)
        if view == 'district_facs' and 'fac_positions' in locals():
            for fac in [f for f in store_facs if _FACILITY_DISTRICT.get(f) == focus_dist]:
                pos = fac_positions.get(fac)
                if pos:
                    focus_points.append(pos)
        if focus_points:
            xs = [p[0] for p in focus_points]
            ys = [p[1] for p in focus_points]
            pad_x = max((max(xs) - min(xs)) * 0.12, 0.03)
            pad_y = max((max(ys) - min(ys)) * 0.12, 0.03)
            x_range = [max(-0.02, min(xs) - pad_x), min(1.02, max(xs) + pad_x)]
            y_range = [max(-0.02, min(ys) - pad_y), min(y_scale + 0.02, max(ys) + pad_y)]

    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode='markers', showlegend=True,
        marker=dict(
            size=10, color=[0], cmin=0, cmax=100, colorscale=HEATMAP_CS,
            colorbar=dict(
                thickness=14,
                title=dict(text='Coverage %', side='right', font=dict(size=9, color=DIM)),
                tickfont=dict(size=9, color=DIM),
                tickvals=[0, 65, 80, 100],
                ticktext=['0%', '65%', '80%', '100%'],
                len=0.8,
            ),
        ),
        hoverinfo='skip',
    ))

    title = (f'{selected_dist} District Coverage Map' if view == 'by_district' and selected_dist else 'District Coverage Map') if view == 'by_district' else (
        'Facility Coverage Map' if view == 'by_facility' else f'{focus_dist} Facility Coverage Map'
    )
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG, height=680, margin=dict(l=10, r=10, t=34, b=10),
        font=dict(family=FONT, color=TEXT, size=11), hoverlabel=dict(bgcolor='#fff', bordercolor=BORDER, font_size=11),
        hovermode='closest', dragmode='pan',
        xaxis=dict(visible=False, range=x_range, fixedrange=False),
        yaxis=dict(visible=False, range=y_range, fixedrange=False, scaleanchor='x', scaleratio=1),
        transition=dict(duration=450, easing='cubic-in-out'),
        annotations=[dict(
            x=0.01, y=1.03, xref='paper', yref='paper', text=title, showarrow=False, xanchor='left',
            font=dict(size=15, color=TEXT, family=FONT),
        )],
    )
    return fig


# # MNID right panel with Malawi shape and indicator stats

def _build_district_treemap(stored: dict, view: str, year: str,
                             district: str | None = None,
                             sel_inds: list | None = None) -> go.Figure:
    """Treemap of districts/facilities colored by avg indicator coverage - looks like the screenshot."""
    district_avgs = stored.get('district_avgs', {}).get(year, {})
    current_fac   = stored.get('current_fac', '')
    current_dist  = stored.get('current_district', '')
    all_labels    = stored.get('y_labels', [])
    all_targets   = stored.get('y_targets', [])

    if sel_inds:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in sel_inds]
    else:
        rows_idx = list(range(len(all_labels)))

    def _fac_avg(fac_code):
        by_fac = stored.get('by_facility', {}).get(year, {})
        fac_x  = by_fac.get('x', [])
        fac_z  = by_fac.get('z', [])
        key    = f'{fac_code}*' if fac_code == current_fac else fac_code
        if key not in fac_x:
            return None
        ci = fac_x.index(key)
        vals = [fac_z[r][ci] for r in rows_idx
                if r < len(fac_z) and ci < len(fac_z[r])
                and fac_z[r][ci] is not None and fac_z[r][ci] == fac_z[r][ci]]  # exclude NaN
        return round(sum(vals) / len(vals), 1) if vals else None

    dyn_districts = stored.get('all_districts', [])
    # Derive facility list from store
    by_fac_data  = stored.get('by_facility', {}).get(year, {})
    store_fac_x  = by_fac_data.get('x', [])
    dyn_facs     = [f.rstrip('*') for f in store_fac_x]

    if view in ('by_district', 'monthly', 'yearly'):
        labels  = list(dyn_districts)
        parents = [''] * len(labels)
        values  = [1.0] * len(labels)          # equal weight - coverage drives color
        covs    = [district_avgs.get(d) for d in labels]
        hl_set  = {current_dist} if view in ('monthly', 'yearly') else set(labels)

    elif view == 'by_facility':
        fac_labels  = [f'{_FACILITY_NAMES.get(f, f)}*' if f == current_fac else _FACILITY_NAMES.get(f, f) for f in dyn_facs]
        labels  = list(dyn_districts) + fac_labels
        parents = ([''] * len(dyn_districts) +
                   [_FACILITY_DISTRICT.get(f, '') for f in dyn_facs])
        d_covs  = [district_avgs.get(d) for d in dyn_districts]
        f_covs  = [_fac_avg(f) for f in dyn_facs]
        covs    = d_covs + f_covs
        values  = [1.0] * len(dyn_districts) + [1.0] * len(dyn_facs)
        hl_set  = set(labels)

    elif view == 'district_facs':
        dist_filter = district or current_dist
        facs = [f for f in dyn_facs if _FACILITY_DISTRICT.get(f) == dist_filter]
        labels  = [f'{_FACILITY_NAMES.get(f, f)}*' if f == current_fac else _FACILITY_NAMES.get(f, f) for f in facs]
        parents = [''] * len(labels)
        values  = [1.0] * len(labels)
        covs    = [_fac_avg(f) for f in facs]
        hl_set  = set(labels)

    else:
        labels, parents, values, covs, hl_set = [], [], [], [], set()

    texts  = [f'{_display_pct(c):.0f}%' if c is not None else 'No data' for c in covs]
    colors = [_cov_color(c) if c is not None else '#C8C5BC' for c in covs]
    opacities = [1.0 if lbl in hl_set else 0.45 for lbl in labels]
    final_colors = []
    for col, op in zip(colors, opacities):
        final_colors.append('#D6D3CB' if op < 1.0 else col)

    if not labels:
        fig = go.Figure()
        fig.update_layout(paper_bgcolor=BG, height=200,
                          margin=dict(l=0, r=0, t=0, b=0))
        return fig

    fig = go.Figure(go.Treemap(
        labels=labels,
        parents=parents,
        values=values,
        marker=dict(
            colors=final_colors,
            line=dict(width=2, color='white'),
            cornerradius=4,
        ),
        text=texts,
        customdata=covs,
        hovertemplate='<b>%{label}</b><br>Avg coverage: %{text}<extra></extra>',
        textposition='middle center',
        textfont=dict(size=11, color=TEXT, family=FONT),
        texttemplate='<b>%{label}</b><br>%{text}',
        pathbar=dict(visible=False),
        tiling=dict(squarifyratio=1.5),
    ))

    fig.update_layout(
        paper_bgcolor=BG,
        margin=dict(l=0, r=0, t=4, b=0),
        height=200,
        showlegend=False,
        font=dict(family=FONT),
    )
    return fig


def _build_malawi_panel(stored: dict, view: str, year: str,
                        district: str | None = None,
                        sel_inds: list | None = None) -> list:
    district_avgs    = stored.get('district_avgs', {}).get(year, {})
    current_district = stored.get('current_district', '')
    all_labels       = stored.get('y_labels', [])
    all_targets      = stored.get('y_targets', [])

    # Apply indicator selection filter
    if sel_inds:
        rows_idx = [i for i, lbl in enumerate(all_labels) if lbl in sel_inds]
    else:
        rows_idx = list(range(len(all_labels)))
    y_labels  = [all_labels[i] for i in rows_idx]
    y_targets = [all_targets[i] for i in rows_idx]

    # Which district is highlighted
    if view in ('monthly', 'yearly'):
        highlight = current_district
    elif view == 'district_facs':
        highlight = district or current_district
    elif view == 'by_district' and district not in (None, '', 'All'):
        highlight = district
    else:
        highlight = None

    treemap_fig  = _build_district_treemap(stored, view, year, district, sel_inds)
    malawi_panel = dcc.Graph(
        id='mnid-malawi-treemap',
        figure=treemap_fig,
        config={'displayModeBar': True, 'responsive': True, 'modeBarButtonsToRemove': ['select2d', 'lasso2d', 'autoScale2d'], 'toImageButtonOptions': {'format': 'png', 'scale': 2}},
        style={'marginBottom': '4px', 'height': '170px'},
    )

    # Stats from selected view data
    if view == 'monthly':
        data = stored.get('monthly', {}).get(year, {})
        view_title = 'This facility - monthly'
    elif view == 'by_facility':
        data = stored.get('by_facility', {}).get(year, {})
        view_title = 'All facilities'
    elif view == 'by_district':
        data = stored.get('by_district', {}).get(year, {})
        view_title = f'{district} district' if district not in (None, '', 'All') else 'All districts'
    elif view == 'district_facs':
        dist = district or current_district
        data = stored.get('by_district_facs', {}).get(dist, {}).get(year, {})
        view_title = f'{dist} - district facilities'
    elif view == 'yearly':
        data = stored.get('yearly') or {}
        view_title = 'Year-over-year'
    else:
        data = {}; view_title = ''

    z_raw = data.get('z', [])
    z = [z_raw[i] for i in rows_idx if i < len(z_raw)]
    x = data.get('x', [])

    all_vals    = [v for row in z for v in row if v is not None]
    overall_avg = round(sum(all_vals) / len(all_vals), 1) if all_vals else None

    ind_stats = []
    for ii, (lbl, tgt) in enumerate(zip(y_labels, y_targets)):
        if ii < len(z):
            vals = [z[ii][jj] for jj in range(len(x))
                    if jj < len(z[ii]) and z[ii][jj] is not None]
            if vals:
                avg = round(sum(vals) / len(vals), 1)
                ind_stats.append({'label': lbl, 'target': tgt, 'avg': avg,
                                  'on_target': avg >= tgt})

    on_tgt  = sum(1 for s in ind_stats if s['on_target'])
    ind_rows = []
    for s in sorted(ind_stats, key=lambda x: -x['avg'])[:12]:
        col = _cov_color(s['avg'])
        ind_rows.append(html.Div(style={
            'display': 'flex', 'alignItems': 'center', 'gap': '6px',
            'padding': '3px 0', 'borderBottom': f'0.5px solid {GRID_C}',
        }, children=[
            html.Div(style={'flex': '1', 'minWidth': '0'}, children=[
                html.Div(s['label'], style={
                    'fontSize': '9px', 'color': DIM,
                    'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap',
                }),
                html.Div(style={'height': '2px', 'background': GRID_C,
                                'borderRadius': '1px', 'marginTop': '2px'}, children=[
                    html.Div(style={'width': f'{min(s["avg"], 100):.0f}%', 'height': '100%',
                                    'background': col, 'borderRadius': '1px', 'width': f'{_display_pct(s["avg"]):.0f}%'}),
                ]),
            ]),
            html.Div(style={'textAlign': 'right', 'flexShrink': '0'}, children=[
                html.Span(f'{_display_pct(s["avg"]):.0f}%',
                          style={'fontSize': '10px', 'fontWeight': '600', 'color': col}),
                html.Span(' OK' if s['on_target'] else '',
                          style={'fontSize': '9px', 'color': OK_C}),
            ]),
        ]))

    # Colour legend
    legend_items = [
        (OK_C, '>=80% on target'),
        (WARN_C, '65-79% watch'),
        (DANGER_C, '<65% needs action'),
    ]
    legend = html.Div(style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '5px',
                              'marginTop': '8px', 'marginBottom': '6px'}, children=[
        html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': '3px'}, children=[
            html.Div(style={'width': '8px', 'height': '8px', 'borderRadius': '50%',
                            'backgroundColor': c, 'flexShrink': '0'}),
            html.Span(l, style={'fontSize': '9px', 'color': DIM}),
        ])
        for c, l in legend_items
    ])

    # Volume counts for this facility
    counts_for_year = stored.get('counts', {}).get(year, {})
    count_items = []
    for label, val in counts_for_year.items():
        if val > 0:
            count_items.append(html.Div(style={
                'display': 'flex', 'justifyContent': 'space-between',
                'padding': '2px 0', 'borderBottom': f'0.5px solid {GRID_C}',
            }, children=[
                html.Span(label, style={'fontSize': '9px', 'color': DIM}),
                html.Span(f'{val:,}', style={'fontSize': '10px', 'fontWeight': '600',
                                             'color': INFO_C}),
            ]))
    counts_block = html.Div(children=count_items, style={'marginBottom': '8px'}) if count_items else None

    return [
        html.Div('MALAWI COVERAGE', className='mnid-section-lbl'),
        malawi_panel,
        *(([html.Div('ENCOUNTER VOLUMES', className='mnid-section-lbl'), counts_block])
          if counts_block else []),
        legend,
        html.Div(style={'display': 'flex', 'justifyContent': 'space-between',
                        'alignItems': 'baseline', 'marginBottom': '4px'}, children=[
            html.Span(view_title, style={'fontSize': '10px', 'color': MUTED}),
            html.Span(f'{_display_pct(overall_avg):.0f}%' if overall_avg is not None else '-',
                      style={'fontSize': '18px', 'fontWeight': '700',
                             'color': _cov_color(overall_avg)}),
        ]),
        html.Div(f'{on_tgt}/{len(ind_stats)} indicators on target',
                 style={'fontSize': '10px', 'color': MUTED, 'marginBottom': '6px'}),
        html.Div('INDICATOR BREAKDOWN', className='mnid-section-lbl'),
        html.Div(style={'overflowY': 'auto', 'maxHeight': '290px'}, children=ind_rows),
    ]