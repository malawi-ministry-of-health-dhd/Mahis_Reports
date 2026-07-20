# HMIS/DHIS2 and MNH Dashboard Architecture

Date: 2026-07-20

## Purpose

This document explains how Malawi HMIS DHIS2 aggregate data moves into the MNID/MNH
dashboard, how it is stored and filtered, and which parts are currently operational.
The central design rule is that dashboard page loads never call DHIS2 directly.
DHIS2 is accessed by a controlled synchronization process, and the dashboard reads
validated local Parquet files.

## Architecture overview

```text
Malawi HMIS DHIS2
        |
        | HTTPS + read-only runtime credentials
        v
DHIS2 synchronization layer (mnid/dhis2)
        |
        +--> raw request/response audit
        |
        v
Header-driven normalization
        |
        v
Indicator calculations and validation
        |
        +--> failed attempt status (does not replace good data)
        |
        v
Atomic local Parquet publication
        |
        v
MNID local store and renderer
        |
        v
MNH Beginnings -> MNH HMIS test
        |
        v
KPI cards, trends, district comparison, facility table
```

## Two DHIS2 data paths

The implementation currently has two related but separate paths.

### Twenty-five-indicator HMIS dashboard path

This is the working dashboard path currently visible to users.

```text
DHIS2 Analytics API
  -> python -m mnid.dhis2.sample_sync
  -> mnid/data/dhis2/aggregates/hmis_test.parquet
  -> MNH Program
  -> MNH Beginnings
  -> MNH HMIS test
```

The current local snapshot contains real DHIS2 aggregate values, not generated demo
values. It contains 232,769 calculated aggregate rows, 25 indicators, 867 reporting
organisation units, 32 districts, and 14 monthly periods from April 2025 through May
2026. It preserves 65,721 explicitly reported zero values.

The indicators are organized into three dashboard domains:

- **Births and outcomes (7):** Live Births, Total Births, Fresh Stillbirths,
  Macerated Stillbirths, Maternal Deaths, Neonatal Deaths, and Stillbirths.
- **Antenatal care (10):** ANC Visits, Blood pressure measured, Tested for HIV,
  Screened for syphilis, At least 4 ANC contacts, Tetanus doses (2+), New ANC
  registrations, Started ANC in first trimester, Received 120+ FeFo tablets, and
  Received ITN during ANC.
- **Delivery and newborn care (8):** Uterotonic given after birth, Bag-mask
  ventilation for newborns not breathing, Vitamin K at birth, Facility deliveries,
  Delivered at this facility, Delivered at home or in transit, Delivered by skilled
  attendant, and Normal vaginal delivery.

The snapshot is cached. It is not refreshed when a user opens or filters the page.
New or corrected DHIS2 submissions become visible only after another successful
sample synchronization.

### Full indicator publication path

The production-oriented path reads the converted 52-indicator mapping, resolves its
78 unique atomic DHIS2 operands, retrieves them in bounded batches, calculates derived
indicators, and applies a completeness validation gate before publication.

```text
MNH mapping workbook
  -> deterministic indicators.json
  -> query planner (dx x periods x organisation units)
  -> secure Analytics client
  -> normalized atomic values
  -> derived calculations
  -> validation gate
  -> aggregates/current.parquet (only after validation succeeds)
```

The latest full publication attempt remains rejected because required operands were
missing. This does not invalidate the 25-indicator snapshot and does not overwrite
any last-known-good production file.

## Main components

| Component | Responsibility |
|---|---|
| `mnid/dhis2/settings.py` | Loads HTTPS endpoint, credentials, periods, batch sizes, timeouts, and storage paths from environment variables. |
| `mnid/dhis2/client.py` | Performs authenticated Analytics requests with TLS verification, timeouts, typed failures, and bounded retries. |
| `mnid/dhis2/mappings.py` | Validates indicators, dependencies, operands, and organisation-unit configuration. |
| `mnid/dhis2/ingestion.py` | Plans batches, records audit responses, parses values, calculates indicators, validates, and publishes atomically. |
| `mnid/dhis2/storage.py` | Writes raw, normalized, calculated, and last-known-good Parquet data safely. |
| `mnid/dhis2/sample_sync.py` | Retrieves 36 required atomic operands in bounded batches, calculates 25 dashboard indicators, and refreshes the controlled facility-level snapshot. |
| `mnid/dashboards/MNH-HMIS-Test/layout.py` | Reads the cached sample, applies filters, and builds cards, charts, and the facility table. |
| `mnid/views/renderer.py` | Routes MNH tabs and provides the HMIS-only fallback when legacy MAHIS data is absent. |
| `pages/home.py` | Resolves URL/user scope, date range, district/facility filters, and selects the MNH renderer. |

## Organisation-unit model

The discovered configuration contains 10,406 DHIS2 organisation units across five
native levels: national, zone, district, facility, and community. The working sample
queries the homogeneous facility level (`LEVEL-4`) and retains DHIS2 UID, name,
district, and proposed local facility code in each aggregate row.

Using one level per synchronization prevents totals from being duplicated by mixing
parent and child values. The proposed local crosswalk remains subject to governance
approval; DHIS2 UIDs remain the authoritative keys in the cached sample.

## Filtering and aggregation behavior

The dashboard reads `hmis_test.parquet` once per render operation and applies:

- start and end reporting period;
- selected district;
- selected facility name, DHIS2 UID, or mapped facility code; and
- indicator grouping.

The visualization structure follows the MNID Country Profile design language: a dark
scope and reporting-period header, priority alert, scope band, current-period summary
cards, and a dedicated labeled monthly run-chart card for each of the 25 indicators.
Charts are grouped under Births and Outcomes, Antenatal Care, and Delivery and Newborn
Care, followed by priority-outcome district ranking and a facility drill-down table.
The indicator cards reuse the same `mnid/components/run_charts.py` payload and callback
as Country Profile, including consistent styling, captions, and time-grain controls.
The source grain is monthly; quarterly and yearly views are rollups of monthly values,
while a weekly selection cannot create true weekly source reporting from monthly DHIS2
aggregates.
KPI cards sum each indicator over the active
scope. Monthly charts group by reporting month and indicator. District comparisons sum
within district. The facility table retains facility, district, domain, indicator, and
value and supports client-side sorting and filtering.

Explicit zero is retained as zero. A missing facility-period row remains missing and
is not silently converted into zero. Percentage indicators in the full pipeline are
recalculated from summed numerators and denominators; facility percentages must not be
averaged directly.

## Application behavior without legacy MAHIS data

The wider application normally expects `data/<route>/parquet` from MAHIS/OpenMRS.
In a DHIS2-only test environment that file can be absent. The application therefore:

1. skips the optional legacy MNID aggregation job;
2. initializes the date range from the HMIS snapshot;
3. allows the demo user and URL state to resolve before rendering;
4. routes the Maternal Health dashboard to an HMIS-only Beginnings shell; and
5. renders the MNH HMIS test without querying the absent legacy Parquet file.

Other legacy programme dashboards still require their normal MAHIS/OpenMRS source.

## Storage layout

```text
mnid/data/dhis2/
  raw/<sync-run-id>/                 request metadata and raw API responses
  normalized/<sync-run-id>/          normalized values and validation report
  aggregates/current.parquet         validated full indicator publication
  aggregates/current_metadata.json   successful publication metadata
  aggregates/hmis_test.parquet       25-indicator dashboard snapshot
  status/current.json                latest full synchronization attempt
```

Runtime data is excluded from Git. Deployments must synchronize or securely provision
the required Parquet snapshot after checking out the application.

## Security boundaries

- Live credentials are supplied only through `MNH_DHIS2_USERNAME` and
  `MNH_DHIS2_PASSWORD` environment variables.
- Credentials and authorization headers are not stored in Git, Parquet, status files,
  audit logs, or this documentation.
- The DHIS2 base URL must use HTTPS and TLS verification defaults to enabled.
- The dashboard renderer has no credentials and performs no network calls.
- The service account should have read-only access limited to approved data-view
  organisation units and datasets.

## Failure and recovery model

| Failure | Behavior |
|---|---|
| DHIS2 timeout, 429, or server error | Bounded retries are attempted; final failure is recorded. |
| Authentication or permission failure | Synchronization stops with a typed permanent error. |
| Malformed or duplicate Analytics rows | Validation rejects the response. |
| Missing calculation operands | Affected values remain null and full publication can be rejected. |
| Partial batch completion | The run cannot replace the last-known-good output. |
| Dashboard process restart | The local Parquet snapshot remains available without DHIS2 access. |
| Missing legacy MAHIS Parquet | HMIS-only MNH rendering remains available. |

Temporary files are atomically renamed only after successful validation. A failed
attempt updates status separately and does not destroy a previously published dataset.

## Operating the current HMIS test

Supply secrets through an approved runtime environment, then run:

```bash
python -m mnid.dhis2.sample_sync
```

Start the application:

```bash
python3 app.py
```

Open the dashboard URL printed by the application and select **MNH Program**. In a
DHIS2-only environment, the **MNH HMIS test** Beginnings view opens using the cached
period range.

## Live reconciliation

The cached dashboard can be compared with a fresh read-only DHIS2 pull without
publishing or overwriting data:

```bash
python -m mnid.dhis2.compare_live \
  --start-period 202601 \
  --end-period 202605
```

The command retrieves the same atomic operands and organisation-unit level, applies
the same calculations, compares period totals and the latest month for every indicator,
and writes a detailed CSV under the ignored `normalized/comparisons/` runtime folder.
The January–May 2026 reconciliation matched all 25 indicators exactly; see
`mnid/HMIS_DHIS2_VALIDATION_202601_202605.md`.

## Production work still required

1. Approve the organisation-unit crosswalk and dataset ownership.
2. Resolve missing operands and clinically review derived calculations.
3. Identify the authoritative dataset for the remaining PNC and related mappings.
4. Reconcile approved samples against Data Entry/Data Value Sets.
5. Automate synchronization with locking, monitoring, freshness alerts, and secret
   rotation.
6. Display last-successful-sync and validation state prominently in the HMIS test UI.
7. Complete a controlled district backfill and obtain HMIS data-quality sign-off
   before national production publication.
