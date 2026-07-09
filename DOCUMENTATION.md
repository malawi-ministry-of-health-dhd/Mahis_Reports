# MaHIS Dash Plotly — Documentation

**MaHIS Dash Plotly** is an analytical web platform built with Plotly Dash for the Ministry of Health Information System. It provides interactive dashboards, HMIS reports, program-level clinical reports, and an administrative configuration UI — all driven by data fetched from an OpenMRS-compatible MySQL database and cached locally as Parquet files.

---

## Table of Contents

1. [Installation](#1-installation)
2. [Architecture](#2-architecture)
3. [Working with Dashboards](#3-working-with-dashboards)
4. [Working with HMIS Reports](#4-working-with-hmis-reports)
5. [Working with Program Reports](#5-working-with-program-reports)
6. [Configurations](#6-configurations)

---

## 1. Installation

### Prerequisites

- Python 3.11+
- Ubuntu/Debian Linux (or macOS for development)
- Access to a MySQL database (local or remote via SSH tunnel)
- Optional: Docker and Docker Compose

---

### Method A — Bash Script (Recommended)

**Step 1: Configure the database**

```bash
cp config.example.py config.py
nano config.py
```

Set your database credentials, SSH tunnel parameters, and data start date. Key settings:

```python
USE_LOCALHOST = True       # True for local MySQL, False for SSH tunnel
START_DATE    = '2024-01-01'
LOAD_FRESH_DATA = False    # True forces a full re-fetch on next run
```

**Step 2: Run the install script**

```bash
chmod +x install.sh
./install.sh
```

This installs Ubuntu system packages and Python dependencies inside a virtual environment.

**Step 3: Verify data fetch**

```bash
source venv/bin/activate
python3 data_storage.py
```

On success, Parquet files appear under `data/default/parquet/` and dropdown files under `data/default/dcc_dropdown_json/`.

**Step 4: Schedule automatic data refresh**

```bash
crontab -e
# Add this line:
*/10 * * * * /home/$(whoami)/Mahis_Reports/venv/bin/python3 /home/$(whoami)/Mahis_Reports/data_storage.py >> /home/$(whoami)/Mahis_Reports/log.txt 2>&1
```

**Step 5: Start the application**

Development:
```bash
chmod +x start_dev.sh && ./start_dev.sh
```

Production (Gunicorn):
```bash
chmod +x start_prod.sh && ./start_prod.sh
```

Stop production:
```bash
chmod +x stop.sh && ./stop.sh
```

---

### Method B — Manual / Traditional

```bash
# 1. Install Python 3.11
sudo apt-get update && sudo apt-get install -y python3 python3-pip

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
export DASH_APP_DIR=/var/www/dash_plotly_mahis

# 4. Configure
cp config.example.py config.py
# Edit config.py — set DB_CONFIG, SSH_CONFIG, START_DATE

# 5. Load initial data
python3 data_storage.py

# 6. Schedule data refresh (every 30 minutes)
# */30 * * * * /path/venv/bin/python3 /path/data_storage.py >> /path/log.txt 2>&1

# 7. Run in development
python3 app.py
# → http://localhost:8050

# 8. Run in production
nohup python3 -m gunicorn --workers 4 --bind 0.0.0.0:8050 wsgi:server > gunicorn.log 2>&1 &

# Stop production
pkill -9 gunicorn
```

---

### Method C — Docker

```bash
git clone <repository-url>
cd mahis-dash-plotly
cp config.example.py config.py   # edit credentials

docker-compose up -d

# Monitor logs
docker-compose logs -f mahis-dash

# Check health
docker-compose exec mahis-dash python -c \
  "import requests; print(requests.get('http://localhost:8050/_health').text)"
```

---

### SSH Key Setup

If `USE_LOCALHOST = False`, the app connects through an SSH tunnel. Place your `.pem` key in a folder named `ssh/` at the parent of the project directory. Reference the filename in `config.py`:

```python
SSH_CONFIG = {
    "ssh_host": "bastion-host.example.com",
    "ssh_username": "ubuntu",
    "ssh_pkey": "../ssh/your-key.pem",
    ...
}
```

---

### URL Format

The application uses URL query parameters to identify the current user context:

```
http://localhost:8050/home?route=default&Location=1833&uuid=m3his@dhd&user_level=national
```

| Parameter    | Description                               |
|-------------|-------------------------------------------|
| `route`      | Data route (e.g. `default`, `mahis`)     |
| `Location`   | Facility code or location ID             |
| `uuid`       | User token for authentication            |
| `user_level` | Permission tier (national, district, etc.)|

---

## 2. Architecture

### High-Level Overview

```
MySQL Database (OpenMRS)
        │
        ▼  (SSH tunnel or direct)
  data_storage.py  ────────────────► data/{route}/parquet/*.parquet
        │                            data/{route}/dcc_dropdown_json/dropdowns.json
        │                            data/mnid_aggregates/ (MNID pre-aggregation)
        ▼
   app.py  (Dash multi-page app)
        │
        ├── pages/home.py              → /home
        ├── pages/reports.py           → /hmis_reports
        ├── pages/program_reports.py   → /program_reports
        ├── pages/configurations.py    → /reports_config
        └── pages/login.py             → /login
```

### Component Map

| Layer           | Files                                        | Responsibility                              |
|-----------------|----------------------------------------------|---------------------------------------------|
| **Entry**       | `app.py`, `wsgi.py`                          | Dash app init, routing, server binding      |
| **Config**      | `config.py`                                  | Constants, DB config, SQL queries, column names |
| **Data Pipeline** | `data_storage.py`, `db_services.py`        | Fetch from DB, store as Parquet             |
| **Dashboard**   | `pages/home.py`, `helpers/helpers.py`        | KPI metrics, chart layout, date filtering   |
| **Visualizations** | `helpers/visualizations.py`              | Chart generation (12 chart types)           |
| **HMIS Reports** | `pages/reports.py`, `helpers/reports_class.py` | Report tables, drill-down, export         |
| **API**         | `helpers/api_routes.py`                      | REST endpoints for external integrations   |
| **Program Reports** | `pages/program_reports.py`              | Clinical/program reports with date range   |
| **Configurations** | `pages/configurations.py`, `helpers/modal_functions.py` | Admin UI, dashboard CRUD, user management |
| **MNID Module** | `mnid/`                                      | Maternal/Neonatal Indicator Dashboard      |

### Data Storage Layout

```
data/
├── {route}/                  ← one folder per data route (default, mahis, etc.)
│   ├── parquet/              ← raw observation data as Parquet
│   ├── single_tables/        ← auxiliary lookup tables
│   └── dcc_dropdown_json/
│       ├── dropdowns.json    ← program, encounter, concept, gender, drug lists
│       └── facilities_dropdowns.json
├── visualizations/
│   ├── validated_dashboard.json       ← active dashboard config
│   └── validated_prog_reports.json    ← active program report config
├── mnid_aggregates/
│   ├── indicator_aggregates.parquet   ← pre-computed MNID coverage
│   └── meta.json
├── hmis_reports.json                  ← HMIS report template registry
├── program_reports.json               ← program report template registry
└── dashboard_payload_template.json    ← GUI template schema
```

### Technology Stack

| Component        | Library/Tool                                |
|-----------------|---------------------------------------------|
| Web framework   | Plotly Dash 3.3+                            |
| UI components   | Dash Mantine Components, Dash Bootstrap Components |
| Icons           | DashIconify (`lucide:*` icon set)           |
| Charts          | Plotly Express + Graph Objects              |
| Data querying   | DuckDB (on Parquet)                         |
| Data storage    | Apache Parquet (via PyArrow)                |
| Database        | MySQL (OpenMRS schema)                      |
| SSH tunneling   | `sshtunnel` + `paramiko`                    |
| PDF export      | ReportLab                                   |
| Excel I/O       | OpenPyXL                                    |
| Production server | Gunicorn (WSGI)                           |
| Containerisation| Docker + Docker Compose                     |

---

## 3. Working with Dashboards

### Overview

The main dashboard at `/home` renders KPI metric cards and data visualisation charts driven entirely by a JSON configuration file (`data/visualizations/validated_dashboard.json`). No code changes are needed to add or modify a dashboard — everything is configured through the JSON or the Configuration GUI.

### Page Entry Point: `pages/home.py`

When a user opens `/home`, the page:

1. Reads URL parameters (`route`, `Location`, `uuid`, `user_level`).
2. Determines the active date window (default: **Today**).
3. Loads the Parquet data for the selected route and date range.
4. Passes the data to `build_metrics_section()` and `build_charts_section()` from `helpers/helpers.py`.
5. Renders the assembled layout.

**Date Range Options**

```python
RELATIVE_DAYS = [
    'Today', 'Yesterday', 'Last 7 Days', 'Last 30 Days',
    'This Week', 'Last Week', 'This Month', 'Last Month'
]
```

**Caching Strategy**

The page maintains two in-memory caches to avoid re-querying Parquet on every interaction:

```python
_mnid_full_data_cache:      dict  # MNID data (max 6 entries)
_dashboard_data_cache:      dict  # Dashboard data (max 4 entries)
```

A `_dataset_version_token()` hash (based on Parquet file modification times) is used as the cache key, ensuring the cache is automatically invalidated when `data_storage.py` writes fresh data.

### Dashboard Configuration: `validated_dashboard.json`

The JSON file has two top-level sections:

```json
{
  "counts": [...],   ← KPI metric cards (left panel)
  "charts": [...]    ← Chart sections (main area)
}
```

#### `counts` — KPI Metric Cards

Each object in `counts` produces one metric card:

```json
{
  "id": "total_patients",
  "label": "Total Patients",
  "measure": "count_unique",
  "unique_column": "person_id",
  "filters": [
    { "column": "Program", "value": "HIV" }
  ]
}
```

| Field           | Description                                                  |
|----------------|--------------------------------------------------------------|
| `id`            | Unique identifier                                           |
| `label`         | Display name on the card                                    |
| `measure`       | `count`, `count_unique`, `sum`, `percentage`, `calculated`  |
| `unique_column` | Column used for deduplication (usually `person_id`)         |
| `filters`       | Array of `{column, value}` filter conditions (AND logic)    |

#### `charts` — Chart Sections

Each object in `charts` defines a section heading with one or more chart items:

```json
{
  "section_title": "Enrollment Trends",
  "chart_items_per_row": 2,
  "items": [
    {
      "chart_type": "line",
      "title": "Monthly Enrollments",
      "date_col": "Date",
      "y_col": "person_id",
      "aggregation": "count_unique",
      ...
    }
  ]
}
```

**Supported chart types:**

| `chart_type`     | Function called                        | Key fields                             |
|-----------------|----------------------------------------|----------------------------------------|
| `column`         | `create_column_chart()`               | `x_col`, `y_col`, `aggregation`       |
| `line`           | `create_time_line_chart()`            | `date_col`, `y_col`, `aggregation`    |
| `pie`            | `create_pie_chart()`                  | `names_col`, `values_col`             |
| `bar`            | `create_horizontal_bar_chart()`       | `label_col`, `value_col`, `top_n`     |
| `histogram`      | `create_age_gender_histogram()`       | `age_col`, `gender_col`               |
| `new_returning`  | `create_new_returning_chart()`        | `unique_column`, `date_col`           |
| `pivot`          | `create_pivot_table()`                | `index_col`, `columns`, `values`      |
| `crosstab`       | `create_crosstab_table()`             | `index_col`, `columns`, `values`      |
| `linelist`       | `create_line_list()`                  | `group_cols`, `group_filters`         |
| `sankey`         | `create_sankey_diagram()`             | `source_col`, `target_col`            |

### Dashboard Builder Functions: `helpers/helpers.py`

```
build_metrics_section(filtered, filtered_data_range, delta_days, data_path, counts_config, url_object)
│
├── create_count_from_config()        ← applies filters, returns count + patient IDs
└── Returns: list of KPI card Div elements

build_charts_section(filtered, data_opd, delta_days, data_path, sections_config)
│
└── build_section_items()             ← iterates chart items in a section
    │
    └── build_single_chart()          ← routes to the correct chart creator
        │
        ├── create_line_chart_from_config()
        ├── create_pie_chart_from_config()
        ├── create_column_chart_from_config()
        ├── create_bar_chart_from_config()
        ├── create_histogram_from_config()
        ├── create_pivot_table_from_config()
        ├── create_crosstab_from_config()
        ├── create_linelist_from_config()
        └── create_sankey_from_config()
```

### Visualisation Functions: `helpers/visualizations.py`

All chart functions follow a consistent signature pattern:

```python
create_column_chart(
    query_filter,     # pre-filtered DataFrame or DuckDB query filter
    data_path,        # path to Parquet data directory
    x_col,            # categorical column for x-axis
    y_col,            # numeric column for y-axis
    title,            # chart title
    x_title,          # x-axis label
    y_title,          # y-axis label
    aggregation,      # 'count', 'count_unique', 'sum'
    unique_column,    # dedup column (for count_unique)
    filters=[],       # [{column, value}, ...]
    ...
)
```

**Filter Processing**

Filters in `visualizations.py` are processed through `_apply_filter()` which supports:

- **Exact match:** `{"column": "Gender", "value": "Female"}`
- **List match:** `{"column": "Program", "value": ["HIV", "TB"]}`
- **Range:** `{"column": "Age", "value": {"min": 15, "max": 49}}`
- **Calculated fields:** `apply_calculated_fields()` allows derived columns via expressions before filtering

**Deduplication**

By default, charts count all rows. When `unique_column` is set (e.g. `person_id`), the chart deduplicates to count distinct patients.

**Theme Constants**

Charts use a shared green-first theme defined at the top of `visualizations.py`:

```python
THEME = {
    "primary": ["#006401", "#03FAD5", "#8A5A01", "#f59e0b", "#0d9488"],
    "greens":  ["#006401", "#1a7a1a", "#2e8f2e", "#43a443", ...],
    "single":  "#006401",
}
```

### Dashboard Template Schema: `dashboard_payload_template.json`

Located at `data/dashboard_payload_template.json`, this file defines the required structure for every object type in the dashboard JSON. The Configuration GUI reads this template to validate user input before writing to `validated_dashboard.json`.

---

## 4. Working with HMIS Reports

### Overview

The HMIS Reports page at `/hmis_reports` renders structured facility-level reports defined as Excel templates stored in `data/hmis_reports.json`. Reports support weekly, monthly, quarterly and bi-annual periods, XLSX/PDF export, and drill-down to patient-level detail.

### Page: `pages/reports.py`

**User workflow:**

1. Select a **Program** (e.g. HIV, TB, MCH).
2. Select a **Report Name** from the filtered list.
3. Choose **Period Type** (Weekly / Monthly / Quarterly / Bi-Annual).
4. Choose **Year** and the specific period (week/month/quarter).
5. Click **Generate** to compute and display the report table.
6. Export via **XLSX** or **PDF** buttons.
7. Click a value cell to open a patient-level drill-down modal.

**Period type configuration:**

```python
relative_week     = [1..52]
relative_month    = ['January', 'February', ..., 'December']
relative_quarter  = ['Q1', 'Q2', 'Q3', 'Q4']
relative_biannual = ['H1', 'H2']
```

### Report Engine: `helpers/reports_class.py`

The `ReportTableBuilder` class processes a report request:

```python
builder = ReportTableBuilder(
    excel_path         = "path/to/template.xlsx",
    report_start_date  = "2024-01-01",
    report_end_date    = "2024-01-31",
    data_route         = "default",
    location           = "1833",
    dhis2_period       = "202401",
    report_design      = {...},
    report_filters     = {...},
)
```

**Excel Template Structure**

Each report template is an `.xlsx` file with three sheets:

| Sheet            | Contents                                                         |
|-----------------|------------------------------------------------------------------|
| `REPORT_NAME`    | Report metadata (name, program, period type)                    |
| `VARIABLE_NAMES` | Row labels mapped to filter/variable names                      |
| `FILTERS`        | Filter definitions: measure type, column-value pairs, numerator/denominator |

**Supported Measure Types**

| Measure              | Description                                        |
|---------------------|----------------------------------------------------|
| `count`              | Row count after applying filters                  |
| `count_unique`       | Distinct person count                             |
| `sum`                | Sum of a numeric column                           |
| `percentage`         | `(numerator / denominator) × 100`                |
| `literal`            | Hard-coded value                                  |
| `count_set`          | Count where multiple conditions hold simultaneously |
| `cohort_count`       | Count within a defined cohort period              |
| `cohort_sum`         | Sum within a cohort                               |
| `cohort_count_set`   | Count-set within a cohort                         |

**Computation Flow**

```
builder._build_filters_map()          ← parses FILTERS sheet into dict
    │
    └── _compute_value_from_filter()  ← for each data row in VARIABLE_NAMES
        │
        ├── create_count_sets()       ← for count_set measures
        ├── create_sum()              ← for sum/cohort_sum measures
        └── cache result              ← avoids recomputing duplicate filters
```

The base filter applied to every computation:

```sql
Date BETWEEN '{start}' AND '{end}'
AND Facility_CODE = {location}
```

### Patient Drill-Down Modal

When a user clicks a non-zero value cell, the page opens a paginated modal showing the underlying patient list. Each patient row is clickable to see their encounter history. Navigation uses **Previous / Next** page buttons.

### REST API for External Access: `helpers/api_routes.py`

Both HMIS aggregate reports and clinical program reports are accessible via a REST API registered with Flask through `register_api_routes(server)`.

**Authentication**

All endpoints require a token. It is resolved from the request in this priority order:

```
1. Authorization: Bearer <token>    (header)
2. X-API-Key: <token>               (header)
3. ?token=<token>                   (query parameter)
4. ?uuid=<token>                    (query parameter, legacy)
```

Tokens are validated against `user_properties.json` in the data route directory or the `ALLOWED_API_UUIDS` set in `config.py`. An unauthorized request returns `HTTP 403`.

**Endpoints**

| Method | Endpoint                | Description                                                 |
|--------|------------------------|-------------------------------------------------------------|
| GET    | `/api/`                 | Lists all available endpoints and supported auth methods   |
| GET    | `/api/reports`          | Lists available HMIS report templates (non-archived)       |
| GET    | `/api/datasets`         | Returns a computed HMIS report for a given period          |
| GET    | `/api/clinicalReports`  | Returns program/clinical report data for a date range      |

---

#### `GET /api/reports`

| Parameter | Required | Description                    |
|----------|----------|--------------------------------|
| `route`   | No       | Data route (default: `default`) |

**Response:**
```json
{
  "reports": [
    { "report_id": "hiv_monthly", "report_name": "HIV Monthly Report", "date_updated": "2024-01-15" }
  ]
}
```

---

#### `GET /api/datasets`

Returns a structured HMIS report computed from an Excel template for a given facility and reporting period.

| Parameter     | Required | Example               | Description                              |
|--------------|----------|-----------------------|------------------------------------------|
| `period`      | Yes      | `Monthly:January:2024` | `{Type}:{Value}:{Year}` — Type is `Weekly`, `Monthly`, or `Quarterly` |
| `Location`    | Yes      | `1833`               | Facility code                            |
| `report_name` | Yes      | `hiv_monthly`        | Report `page_name` from `hmis_reports.json` |
| `route`       | No       | `default`            | Data route (defaults to `default`)       |

**Response:**
```json
{
  "report_id": "hiv_monthly",
  "report_name": "HIV Monthly Report",
  "facility_id": "1833",
  "period": "Monthly:January:2024",
  "sections": [
    {
      "section_name": "Testing",
      "data": [
        { "Data Element": "Tested for HIV", "Value": "245", "Code": "HTS_TST" }
      ]
    }
  ]
}
```

---

#### `GET /api/clinicalReports`

Returns patient-level or aggregated clinical report data from `validated_prog_reports.json`. Supports LineList, PivotTable, and CrossTab report types.

| Parameter   | Required | Example        | Description                                                               |
|------------|----------|----------------|---------------------------------------------------------------------------|
| `startDate` | Yes      | `2026-01-01`  | Start of date range (`YYYY-MM-DD`)                                        |
| `endDate`   | Yes      | `2026-12-31`  | End of date range (`YYYY-MM-DD`) — can extend into the future             |
| `report_id` | Yes      | `opd_1`       | Report `id` field from `validated_prog_reports.json`                      |
| `route`     | No       | `default`     | Data route (defaults to `default`)                                        |
| `Location`  | No       | `32,33`       | One or more `Facility_CODE` values, comma-separated. Omit for all facilities |

**Response:**
```json
{
  "report_id": "opd_1",
  "report_name": "GENERAL OPD REGISTER - LINELIST OF OPD PATIENTS",
  "facility_id": "32,33",
  "start_date": "2026-01-01",
  "end_date": "2026-12-31",
  "data": [
    { "Date": "2026-03-15", "Gender": "Female", "Age": "34", "Complaint": "Fever", ... },
    { "Date": "2026-03-15", "Gender": "Male",   "Age": "12", "Complaint": "Cough", ... }
  ]
}
```

When `Location` is omitted, `facility_id` is returned as `"All facilities"`.

**`data` field by report type:**

| Type         | Record structure                                                             |
|-------------|------------------------------------------------------------------------------|
| `LineList`   | One dict per patient row; keys are the configured `cols_order` column names |
| `PivotTable` | One dict per pivot row; keys are the index column and pivoted column headers |
| `CrossTab`   | One dict per crosstab row; multi-level column keys joined with `\|`         |

**Example — PivotTable (`opd_4`):**
```json
{
  "report_id": "opd_4",
  "report_name": "OPD DRUG DISPENSATION REPORT",
  "facility_id": "All facilities",
  "start_date": "2026-01-01",
  "end_date": "2026-12-31",
  "data": [
    { "DRUG": "Paracetamol", "Number of drugs dispensed": "245" },
    { "DRUG": "Amoxicillin", "Number of drugs dispensed": "130" }
  ]
}
```

**Finding available `report_id` values:**

Query `data/visualizations/validated_prog_reports.json` directly, or read the `id` field from each report object. Each report also carries a `program` and `type` field for filtering.

**Example curl calls:**
```bash
# LineList — all facilities
curl "http://localhost:8050/api/clinicalReports?startDate=2026-01-01&endDate=2026-12-31&report_id=opd_1&route=default&uuid=m3his@dhd"

# PivotTable — specific facility
curl "http://localhost:8050/api/clinicalReports?startDate=2026-01-01&endDate=2026-12-31&report_id=opd_4&Location=32&route=default&uuid=m3his@dhd"

# Bearer token auth
curl -H "Authorization: Bearer m3his@dhd" \
  "http://localhost:8050/api/clinicalReports?startDate=2026-01-01&endDate=2026-12-31&report_id=ncd_4&route=default"
```

---

## 5. Working with Program Reports

### Overview

The Program Reports page at `/program_reports` generates tabular clinical/program reports (LineList, PivotTable, CrossTab) defined in `data/visualizations/validated_prog_reports.json`. Unlike HMIS reports (which use Excel templates), program reports are configured entirely through JSON and the GUI in the Configurations page.

### Page: `pages/program_reports.py`

**User workflow:**

1. Select a **Program** from the dropdown.
2. Select a **Report Name** (filtered by program).
3. Choose a **Date Range** using the date picker.
4. Optionally filter by **Health Facility** (multi-select).
5. Click **Generate Report**.
6. Export via XLSX or PDF.

**Controls:**

| Control          | ID                     | Description                       |
|-----------------|------------------------|-----------------------------------|
| Program          | program dropdown       | Filters available reports         |
| Report Name      | report dropdown        | Selects the report config         |
| Date Range       | DatePickerRange        | From / To dates (min: 2023-01-01) |
| Facility Filter  | facility multi-select  | Limits data to selected sites     |
| Generate         | generate button        | Triggers computation              |
| Reset            | reset button           | Clears all selections             |

### Report Configuration: `validated_prog_reports.json`

Each report object supports three types:

#### LineList

A patient-level tabular report with optional grouping and aggregation.

```json
{
  "id": "hiv_linelist_001",
  "report_name": "HIV Patient Register",
  "program": "HIV",
  "type": "LineList",
  "unique_col": "person_id",
  "group_cols1": ["person_id", "given_name", "family_name", "Gender"],
  "group1_filters": [
    { "column": "Program", "value": "HIV" }
  ],
  "group1_aggr": "count",
  "group1_rename": { "person_id": "Patient ID", "given_name": "First Name" },
  "cols_order": ["Patient ID", "First Name", "Last Name", "Gender"],
  "merge_methods": "inner",
  "rename": { "family_name": "Last Name" }
}
```

Multiple groups (`group_cols1`, `group_cols2`, ...) can be defined and merged to produce a combined view.

#### PivotTable

A cross-tabulation with row index, column headers, and aggregated values.

```json
{
  "id": "hiv_pivot_001",
  "report_name": "HIV by Gender and Age Group",
  "program": "HIV",
  "type": "PivotTable",
  "unique_col": "person_id",
  "filters": {
    "index_col": "Age_Group",
    "columns": "Gender",
    "values": "person_id",
    "aggfunc": "count",
    "filter_col1": "Program",
    "filter_val1": "HIV",
    "rename": {},
    "replace": {}
  }
}
```

#### CrossTab

Similar to PivotTable but generates a contingency table with marginal totals.

```json
{
  "type": "CrossTab",
  "filters": {
    "index_col": "District",
    "columns": "Service_Area",
    "values": "person_id",
    "aggfunc": "nunique",
    ...
  }
}
```

### Creating / Editing Program Reports

Use the **Create Program Report** GUI modal accessed from the Configurations page (`/reports_config`). It provides:

- **Left panel:** Report metadata (name, program, type, unique column, authorised users, message).
- **Right panel (LineList):** Dynamic group rows — each group has its own column list, filters, aggregation method, and rename map. Groups can be added (up to 30) or removed (minimum 1).
- **Right panel (PivotTable/CrossTab):** Index column, columns field, values field, aggregation function, filter pairs, and rename/replace maps.

On save, `validated_prog_reports.json` is updated immediately with a timestamp.

---

## 6. Configurations

### Overview

The Configuration page at `/reports_config` is the administrative interface for managing all aspects of the platform — dashboards, report templates, users, data sources, and more. It is accessible only to authorised administrators.

### Navigation Sections

The page is organised into collapsible panels:

| Section                   | Description                                                         |
|--------------------------|---------------------------------------------------------------------|
| **Dashboard Builder**     | Create/edit dashboard KPI cards and charts via GUI                 |
| **Dataset Reports**       | View loaded report configurations and their status                 |
| **Create Dashboard (GUI)** | Modal for building `validated_dashboard.json` object by object    |
| **Create HMIS Report**    | Upload and manage Excel report templates                           |
| **Create HTML Report**    | Drag-and-drop HTML table report designer                           |
| **Create Program Report** | GUI modal for building `validated_prog_reports.json` entries       |
| **User Configuration**    | Create, edit, and delete user accounts and facility assignments    |
| **Data Source Config**    | Manage database connections and SSH tunnel settings               |

---

### Dashboard Builder GUI

Accessed via the **Create Dashboard (GUI)** button. This opens a modal connected to `validated_dashboard.json`.

**Left panel — Object selector:**
- Select an existing dashboard object by ID, or click **New** to create one.
- Objects represent either a KPI count card or a chart item.

**Right panel — Form:**
- Fields are populated from the selected object's JSON structure.
- Available fields are guided by `dashboard_payload_template.json`.
- Field values are constrained to `actual_keys_in_data` from `config.py` (44 columns).
- Dropdown options for Program, Encounter, Gender, concept_name, DrugName are loaded from `dropdowns.json`.

**Input type mapping** (how field types are rendered in the form):

| Data type                       | Form control                            |
|--------------------------------|-----------------------------------------|
| `int`                           | Integer number input                   |
| `date`                          | Date picker                            |
| `text`                          | Text input                             |
| `text,singleselect`             | Single-select dropdown                 |
| `text,singleselect,multiselect` | Multi-select dropdown (from dropdowns) |
| `boolean`                       | Toggle switch                          |

**Save behaviour:** On save, `validated_dashboard.json` is updated immediately and a timestamp notification is shown. On delete, the object is removed and the file is updated.

---

### HMIS Report Template Management

- Upload Excel template files (`.xlsx`) for new HMIS reports.
- Each template must contain `REPORT_NAME`, `VARIABLE_NAMES`, and `FILTERS` sheets (see Section 4 for schema details).
- Uploaded templates are registered in `data/hmis_reports.json`.
- Existing templates can be previewed or deleted from the list.

---

### HTML Report Designer

A drag-and-drop interface for building styled HTML/PDF report templates. Features include:

- Add/remove table rows and columns.
- Merge and split cells.
- Text formatting (Bold, Italic, Left/Centre/Right alignment, Indent/Outdent).
- Add section title rows.
- Variable insertion from the available data columns.
- Filter configuration per section.
- Save to `data/html_reports.json`.

---

### Program Report GUI

Accessed via the **Create Program Report** button. Full details are covered in [Section 5](#5-working-with-program-reports).

Key identifiers:
- Modal: `create-prog-report-modal`
- Save output: `data/visualizations/validated_prog_reports.json`
- Selector: `prog-rpt-selector`
- Group store: `prog-rpt-groups-store` (DCC Store, holds group list in session)

---

### User Configuration

Manage platform users:

- **Create user:** Name, email, assigned facilities, district, program access, role.
- **Edit user:** Update any attribute.
- **Delete user:** Removes from `user_properties.json`.
- **Facility assignment:** Multi-select from available facilities in the current data route.

User properties are stored per data route in `data/{route}/user_properties.json`.

---

### Data Source Configuration

Configure the database connection used by `data_storage.py`:

| Setting         | Description                                  |
|----------------|----------------------------------------------|
| Host            | MySQL server hostname or IP                 |
| Port            | MySQL port (default: 3306)                  |
| Database        | Schema name                                  |
| Username        | DB user                                      |
| Password        | DB password (stored encrypted)              |
| SSH Host        | Bastion server hostname                     |
| SSH Username    | SSH user                                     |
| SSH Key File    | Path to `.pem` private key                  |
| Start Date      | Earliest date to fetch data from            |
| Batch Size      | Records per fetch cycle (default: 1000)     |

Changes are written to `config.py` and take effect on the next `data_storage.py` run.

---

### Callback Architecture (`pages/configurations.py`)

The configurations page contains over 90 Dash callbacks organised into numbered sections (1–13):

| Section | Topic                                              |
|---------|---------------------------------------------------|
| 1       | Modal open/close for dashboard editor             |
| 2       | Dashboard object selector and form population     |
| 3       | KPI count form fields                             |
| 4       | Chart form fields                                 |
| 5       | Section management                                |
| 6       | Filter row management (pattern-matching callbacks)|
| 7       | User configuration panel                         |
| 8       | Data source panel                                 |
| 9       | SSH key management                               |
| 10      | Dataset Reports toggle and close                 |
| 11      | Excel report upload and preview                  |
| 12      | Filter value dropdowns (MATCH callbacks, DuckDB) |
| 13      | Program report modal (open/close, form, save/delete) |

**Pattern-matching callbacks** (`MATCH`, `ALL`) are used extensively for dynamic filter rows and group rows. Each row has a pattern-matched index; the `MATCH` pattern ensures each row's callback operates on only its own index.

**Key stores used:**

| Store ID                  | Purpose                                           |
|--------------------------|---------------------------------------------------|
| `url-params-store`        | Current URL parameters (route, location, uuid)   |
| `prog-rpt-groups-store`   | Program report group rows state                  |
| `rpt-filter-row-store`    | HMIS report filter rows state                    |

---

## Appendix: Key Configuration Constants (`config.py`)

**Column name constants** (used throughout `helpers/` and `pages/`):

```python
DATE_            = 'Date'
PERSON_ID_       = 'person_id'
ENCOUNTER_ID_    = 'encounter_id'
FACILITY_        = 'Facility'
FACILITY_CODE_   = 'Facility_CODE'
DISTRICT_        = 'District'
AGE_GROUP_       = 'Age_Group'
GENDER_          = 'Gender'
PROGRAM_         = 'Program'
CONCEPT_NAME_    = 'concept_name'
VALUE_NUMERIC_   = 'ValueN'
DRUG_NAME_       = 'DrugName'
```

**All 44 available data columns** (`actual_keys_in_data`):

```
person_id, visit_id, date_started, date_stopped, identifier,
patient_identifier_type, given_name, family_name, Gender, birthdate,
AgeDays, Age, Age_Group, person_attribute_name, person_attribute_type,
Home_district, TA, Village, encounter_id, Encounter, Date, location_id,
creator, provider_id, Program, concept_name, obs_datetime, obs_group_id,
accession_number, value_group_id, value_boolean, obs_value_coded,
value_coded_name_id, DrugName, value_datetime, ValueN, Value,
Order_Type, Order_Name, Source_Program, Reporting_Program, Service_Area,
new_revisit, DrugUnits, User, Facility_CODE, Facility, District, month_key
```

---

*Last updated: 2026-07-08*
