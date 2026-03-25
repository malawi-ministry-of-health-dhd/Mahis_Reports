# MNID Indicator Coverage Heatmap — Design Reference

## Overview

The heatmap (`_build_heatmap`) renders a multi-view Plotly `go.Heatmap` inside a
`dcc.Graph`. It gives a compact at-a-glance view of how all tracked indicators
perform across time, facilities, and districts — without requiring page reloads or
Dash callbacks.

All interactivity is achieved through Plotly `updatemenus` (button groups rendered
natively inside the Plotly figure), so the heatmap works in any static or
server-rendered context.

---

## Data Source

```
data/latest_data_opd.parquet
```

Loaded directly inside `_build_heatmap` with:

```python
df_all  = pd.read_parquet('data/latest_data_opd.parquet')
mch_full = df_all[df_all['Program'].str.contains('Maternal|Neonatal', case=False, na=False)]
```

This ensures the heatmap always uses the full cross-facility dataset, independent
of whatever date-filtered slice is passed into the main renderer.

> **Performance note:** The heatmap uses a vectorized `_matrix_by_group` helper
> (one pandas `groupby` per indicator, not one filter per indicator × group).
> This reduces the operation count from O(indicators × groups × 2) to O(indicators × 2),
> bringing build time from ~11 s to ~3 s for 20 indicators × 4 facilities.

### Relevant columns

| Column         | Used for                                     |
|----------------|----------------------------------------------|
| `Program`      | Filter to MCH data                           |
| `Date`         | Month grouping and year filtering            |
| `Facility_CODE`| Per-facility slicing                         |
| `District`     | Per-district aggregation                     |

---

## Indicator Rows (Y-axis)

- Only **tracked** indicators (status = `"tracked"`) appear as rows.
- Rows are ordered by care phase category: **ANC → Labour → Newborn → PNC**.
- Labels are truncated to 28 characters for readability.

---

## Views (X-axis changes per view)

The heatmap has **4 view modes**, each changing what the X-axis represents:

### View 0 — This Facility — Monthly
- **X**: Month labels in `"Mon YY"` format (e.g. `"Oct 25"`), derived from all
  periods present in the current facility's data.
- **Data**: `_cov()` computed for each indicator × each calendar month for the
  current `facility_code` only.
- **X-axis tick angle**: 0 degrees.

### View 1 — District Facilities
- **X**: Facility codes belonging to the **same district** as the current facility.
  The current facility is marked with an asterisk (e.g. `LL040033*`).
- **Data**: `_cov()` computed per indicator × per district-peer facility, across
  the full (or year-filtered) date range.
- **X-axis tick angle**: −40 degrees.

### View 2 — All Districts
- **X**: District names — `Lilongwe`, `Mzuzu`, `Blantyre`.
- **Data**: `_cov()` computed per indicator × per district, aggregating all
  facilities within each district.
- **X-axis tick angle**: −40 degrees.

### View 3 — All Facilities
- **X**: All 4 facility codes. Current facility marked with `*`.
- **Data**: `_cov()` computed per indicator × per facility.
- **X-axis tick angle**: −40 degrees.

---

## Year Filtering

A second row of buttons filters the underlying data by year before computing
coverage values.

| Button | Filter applied                        |
|--------|---------------------------------------|
| All    | No year filter — full date range      |
| 2025   | `mch_full[mch_full['Date'].dt.year == 2025]` |
| 2026   | `mch_full[mch_full['Date'].dt.year == 2026]` |

---

## Trace Pre-computation

All combinations are pre-computed at render time (no callbacks required):

```
12 traces = 4 views × 3 year filters
Trace index = view_idx * 3 + year_idx
```

| view_idx | View name              |
|----------|------------------------|
| 0        | This Facility Monthly  |
| 1        | District Facilities    |
| 2        | All Districts          |
| 3        | All Facilities         |

| year_idx | Year filter |
|----------|-------------|
| 0        | All         |
| 1        | 2025        |
| 2        | 2026        |

Only one trace is visible at a time. The `updatemenus` button callbacks set
`visible` arrays to show the correct trace and hide the other 11.

**Default on load**: trace index 0 (view=Monthly, year=All).

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

Interpretation guide:

| Color          | Coverage range | Meaning             |
|----------------|----------------|---------------------|
| Deep red       | 0–40%          | Well below benchmark|
| Amber          | 40–80%         | Performing          |
| Light green    | 80–88%         | Near target         |
| Deep green     | 88–100%        | On or above target  |
| Grey (no cell) | null / den=0   | No data available   |

Cells with denominator = 0 are stored as `None` so Plotly renders them in the
default "no data" grey colour rather than as 0% (red).

---

## Layout

| Parameter       | Value                                     |
|-----------------|-------------------------------------------|
| `height`        | `max(n_indicators * 26 + 120, 400)` px   |
| `margin.l`      | 220 px (wide left for indicator labels)  |
| `margin.r`      | 100 px (colorbar space)                  |
| `margin.t`      | 90 px (button rows)                      |
| `margin.b`      | 60 px                                     |
| colorbar width  | 14 px                                     |
| colorbar title  | "Coverage %"                              |
| annotation      | "* = current facility" (bottom-right)    |

---

## Hover Template

```
%{y}<br>%{x}: %{z:.0f}%<extra></extra>
```

Example tooltip: `ANC 1st visit coverage\nOct 25: 74%`

---

## Facilities and Districts

| Facility Code | Facility Name         | District   |
|---------------|-----------------------|------------|
| LL040033      | Lilongwe Central      | Lilongwe   |
| BT020011      | Bwaila District       | Lilongwe   |
| MZ120004      | Mzuzu Urban           | Mzuzu      |
| BL050022      | Blantyre South        | Blantyre   |

---

## CSS / Navigation Integration

The heatmap `Div` is assigned `id='mnid-heatmap'` so the sticky navigation bar
can anchor-link to it. Smooth scrolling is enabled globally via
`html { scroll-behavior: smooth; }` in `assets/mnid.css`.

The section anchor offset (`.mnid-section-anchor`) ensures content is not hidden
behind the sticky nav when following anchor links (offset: 60 px).

---

## Extending the Heatmap

To add a new view:
1. Increment the total trace count (currently 12).
2. Add a computation function returning `(x_labels, z_matrix)`.
3. Add a new entry to `view_buttons` in `_build_heatmap`.
4. Update the `_FACILITY_DISTRICT` dict if new facilities are added.

To add a new year filter:
1. Extend `year_filters` list.
2. Recalculate total traces: `n_views × n_years`.
3. Update trace index formula accordingly.
