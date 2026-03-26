# MNID Indicator Coverage Heatmap — Design Reference
> Last updated: 2026-03-26

## Overview

The heatmap (`_coverage_heatmap_section`) renders a multi-view Plotly `go.Heatmap` inside a
`dcc.Graph`. It gives a compact at-a-glance view of how all tracked indicators
perform across time, facilities, and districts.

Interactivity is achieved through:
- **Dash `@callback`** (module-level) for view/year/district filter changes
- **`dcc.Store`** (`id='mnid-heatmap-store'`) to hold all pre-computed matrices
- **`dcc.RadioItems`** styled as tab buttons for view and filter selection
- A **Malawi district panel** (`id='mnid-heatmap-right'`) that updates alongside the heatmap

---

## Data Source

```
data/latest_data_opd.parquet
```

Loaded directly inside `_coverage_heatmap_section`:

```python
df_all   = pd.read_parquet('data/latest_data_opd.parquet')
mch_full = df_all[df_all['Program'].str.contains('Maternal|Neonatal', case=False, na=False)]
```

This ensures the heatmap always uses the full cross-facility dataset, independent
of whatever date-filtered slice is passed into the main renderer.

> **Performance note:** All matrices are pre-computed in `_compute_heatmap_store` using
> vectorized pandas `groupby` (one pass per indicator per year slice), not one filter
> per indicator × group. This keeps build time around 3–4 s for 6 indicators × 4 facilities.

### Relevant columns

| Column         | Used for                                     |
|----------------|----------------------------------------------|
| `Program`      | Filter to MCH data                           |
| `Date`         | Month grouping and year filtering            |
| `Facility_CODE`| Per-facility slicing                         |
| `District`     | Per-district aggregation                     |
| `person_id`    | Unique patient counting (numerator/denominator) |

---

## Indicator Rows (Y-axis)

- Only **tracked** indicators (status = `"tracked"`) appear as rows.
- Rows are ordered by care phase category: **ANC → Labour → Newborn → PNC**.
- Labels are truncated to 32 characters for readability.

---

## Views (X-axis changes per view)

The heatmap has **5 view modes**, selectable via `dcc.RadioItems(id='mnid-heatmap-view')`:

### View: `monthly` — This Facility Monthly
- **X**: Month labels in `"Mon YY"` format, derived from the current facility's data.
- **Data**: Coverage computed per indicator × calendar month for the current `facility_code`.
- **X-axis tick angle**: 0°.

### View: `district_facs` — My District Facilities
- **X**: Facility codes belonging to the **same district** as the current facility.
  Current facility marked with `*` (e.g. `LL040033*`).
- **Data**: Coverage per indicator × per facility, filtered to current district.
- **X-axis tick angle**: −30°.

### View: `by_district` — All Districts
- **X**: District names — `Lilongwe`, `Mzuzu`, `Blantyre`.
- **Data**: Coverage per indicator × per district, aggregating all facilities.
- **X-axis tick angle**: −20°.

### View: `by_facility` — All Facilities
- **X**: All 4 facility codes. Current facility marked with `*`.
- **Data**: Coverage per indicator × per facility, all facilities.
- **X-axis tick angle**: −30°.

### View: `yearly` — Year-over-Year (current facility)
- **X**: Calendar year strings (e.g. `"2025"`, `"2026"`), derived from actual data.
- **Data**: Coverage per indicator × per year for the current facility.
- **X-axis tick angle**: 0°.
- **Availability**: Only shown if the current facility has data across multiple years.

---

## Filters

### Year filter (`id='mnid-heatmap-year'`)

| Option   | Filter applied                                    |
|----------|---------------------------------------------------|
| All years| No year filter — full date range                  |
| 2025     | `Date.dt.year == 2025`                            |
| 2026     | `Date.dt.year == 2026`                            |

> Not applicable to the `yearly` view (which always shows all years by design).

### District filter (`id='mnid-heatmap-district'`)

Only relevant for the `district_facs` view. Selecting a district shows
the heatmap for facilities within that district. Default is the current
facility's district.

---

## Store Pre-computation

All view × year combinations are pre-computed at render time into
`dcc.Store(id='mnid-heatmap-store')`. No server round-trips are needed
for filter changes — only the Dash callback updating the figure.

### Store structure

```python
{
    'y_labels':  [...],            # indicator label strings (truncated to 32 chars)
    'y_targets': [...],            # target % per indicator
    'current_fac':      str,       # current facility code
    'current_district': str,       # current facility's district

    'monthly': {
        'All years': {'x': [...months...], 'z': [[...]], 'tick_angle': 0},
        '2025':      {'x': [...], 'z': [[...]], 'tick_angle': 0},
        '2026':      {'x': [...], 'z': [[...]], 'tick_angle': 0},
    },

    'by_facility': {
        'All years': {'x': [...fac_codes...], 'z': [[...]], 'tick_angle': -30,
                      'districts': [...]},
        '2025':      {...},
        '2026':      {...},
    },

    'by_district': {
        'All years': {'x': ['Lilongwe','Mzuzu','Blantyre'], 'z': [[...]], 'tick_angle': -20},
        ...
    },

    'by_district_facs': {
        'Lilongwe': {'All years': {'x': [...], 'z': [...], 'tick_angle': -30}, '2025': {...}, '2026': {...}},
        'Mzuzu':    {...},
        'Blantyre': {...},
    },

    'yearly': {'x': ['2025','2026'], 'z': [[...]], 'tick_angle': 0},

    'district_avgs': {
        'All years': {'Lilongwe': float_or_None, 'Mzuzu': float_or_None, 'Blantyre': float_or_None},
        '2025':      {...},
        '2026':      {...},
    },
}
```

All values are JSON-serializable primitives (lists, dicts, float, None, str, int).

---

## Callback

```python
@callback(
    Output('mnid-heatmap-graph', 'figure'),
    Output('mnid-heatmap-right', 'children'),
    Input('mnid-heatmap-view',     'value'),
    Input('mnid-heatmap-year',     'value'),
    Input('mnid-heatmap-district', 'value'),
    State('mnid-heatmap-store',    'data'),
    prevent_initial_call=True,
)
def update_heatmap_view(view, year, district, stored): ...
```

The callback reads from the pre-computed store and calls:
- `_build_heatmap_fig(stored, view, year, district)` → Plotly figure
- `_build_malawi_panel(stored, view, year, district)` → right-panel children

---

## Color Logic

Coverage percentages are mapped to a custom 6-stop diverging color scale:

```python
HEATMAP_CS = [
    [0.00, '#FCE4E4'],   # very light red (0%)
    [0.40, '#E24B4A'],   # full red     (40%)
    [0.65, '#BA7517'],   # amber        (65%)
    [0.80, '#FAC775'],   # light amber  (80%)
    [0.88, '#C0DD97'],   # light green  (88%)
    [1.00, '#3B6D11'],   # full green   (100%)
]
```

| Color      | Coverage range | Meaning              |
|------------|----------------|----------------------|
| Deep red   | 0–40%          | Well below benchmark |
| Amber      | 40–65%         | Needs improvement    |
| Light amber| 65–80%         | Performing           |
| Light green| 80–88%         | Near target          |
| Deep green | 88–100%        | On or above target   |
| Grey       | null / den=0   | No data available    |

Cells with denominator = 0 are stored as `None` so Plotly renders them grey.

---

## Malawi District Panel

A stylized Malawi silhouette panel (`_build_malawi_panel`) is displayed to
the right of the heatmap. It consists of 3 stacked `html.Div` blocks
proportioned by approximate geographic area:

| Block     | Height | District  |
|-----------|--------|-----------|
| Mzuzu     | 26%    | Mzuzu     |
| Lilongwe  | 43%    | Lilongwe  |
| Blantyre  | 31%    | Blantyre  |

Each block is colored by the district's average indicator coverage using
`_cov_color(avg)`. The currently selected/relevant district gets a
blue left border (`3px solid #1E6BB8`) as a highlight.

Below the silhouette:
- Overall average coverage %
- Count of indicators on target
- Per-indicator mini progress bars with coverage % label

---

## Layout

| Parameter       | Value                                     |
|-----------------|-------------------------------------------|
| `height`        | `max(n_indicators * 30 + 150, 380)` px   |
| `margin.l`      | 230 px (wide left for indicator labels)  |
| `margin.r`      | 80 px (colorbar space)                   |
| `margin.t`      | 60 px                                    |
| `margin.b`      | 60 px                                    |
| colorbar width  | 14 px                                    |
| colorbar tickvals | `[0, 40, 65, 80, 88, 100]`            |
| colorbar title  | `"Cov %"`                                |
| Cell annotations| Shown when ≤ 8 columns (font size 8px)   |
| Hover template  | `%{y}<br>%{x}: %{z:.1f}%`               |

---

## Facilities and Districts

| Facility Code | Facility Name             | District   |
|---------------|---------------------------|------------|
| LL040033      | Lilongwe Central Hospital | Lilongwe   |
| BT020011      | Bwaila District Hospital  | Lilongwe   |
| MZ120004      | Mzuzu Urban Health Centre | Mzuzu      |
| BL050022      | Blantyre South HC         | Blantyre   |

---

## CSS / Navigation Integration

The heatmap `Div` is assigned `id='mnid-heatmap'` so the sticky navigation bar
can anchor-link to it.

View tab buttons use `dcc.RadioItems` with `labelClassName='mnid-filter-btn'`.
The selected state is styled via the `.mnid-filter-btn` class in `assets/mnid.css`.

---

## Extending the Heatmap

To add a new view:
1. Add pre-computation logic in `_compute_heatmap_store` for the new store key.
2. Add a branch in `_build_heatmap_fig` to read the new key.
3. Add a new `{'label': ..., 'value': ...}` entry to `view_options` in `_coverage_heatmap_section`.

To add a new year filter:
1. Extend `year_options` dict in `_compute_heatmap_store`.
2. Extend `year_opts` list in `_coverage_heatmap_section`.

To add a new facility:
1. Add to `_FACILITY_DISTRICT` dict.
2. Add to `_ALL_FACILITIES` list.
3. Update `_ALL_DISTRICTS` if a new district is introduced.
