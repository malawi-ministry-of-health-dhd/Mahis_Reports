# MNID/MNH DHIS2 Integration Implementation Report

Date: 2026-07-20

## Executive summary

A secure, offline-first DHIS2 Analytics integration has been implemented under
`mnid/`. It converts the supplied mapping workbook into deterministic validated JSON,
plans and executes bounded Analytics queries, preserves audit data, normalizes and
calculates MNH indicators, validates completeness, atomically publishes Parquet, and
provides an opt-in local data source for the MNH-MoH dashboard.

Authenticated Analytics and Data Entry API requests have now been completed. The full
DHIS2 organisation hierarchy is available locally as discovered metadata, four source
Data Entry forms have been identified, and their mappings have been assessed.
Production publication remains blocked pending governance approval of the crosswalk,
resolution of incomplete operands, and management approval of the ingestion model.
Current MaHIS/OpenMRS dashboard behaviour remains the default and is not replaced.

## Scope completed

- MNID-local settings, period handling, typed exceptions, mapping validation, client,
  calculations, validation, ingestion, storage, status, CLI, store, tests, and docs.
- Secure HTTPS-only configuration with environment credentials and verified TLS.
- Batched `dx`, `pe`, and `ou` Analytics query planning.
- Raw audit, normalized atomic data, calculated indicators, validation reports, and
  last-known-good output separated under ignored runtime folders.
- Opt-in DHIS2 dashboard mode without render-time network access.

No files outside `mnid/` were modified by this implementation.

## Existing implementation assessed

The previous shared DHIS2 helper was a report-specific prototype with hard-coded
configuration, disabled TLS verification, broad exception handling, and no MNID
connection. MNID itself used MaHIS/OpenMRS-derived Parquet and locally precomputed
aggregates. The assessment and architecture are recorded in
`mnid/DHIS2_IMPLEMENTATION_ASSESSMENT.md`.

## Architecture implemented

```text
Excel -> deterministic indicator JSON
DHIS2 Analytics -> secure client -> raw audit -> normalized values
-> calculations -> validation gate -> atomic current.parquet
-> cached local store -> opt-in MNH-MoH dashboard
```

A failed request, malformed response, duplicate, missing calculation input, partial
plan, or rejected validation cannot overwrite `current.parquet`.

## Verified DHIS2 reporting sources

Searching similarly named visualizations initially found only three mapped identifiers.
Further inspection confirmed that those visualizations are primarily summary or
reporting-rate products. The authoritative aggregate Data Entry forms are:

| Programme | Dataset | DHIS2 UID | Period | Configured elements | MNH mapping matches |
|---|---|---|---|---:|---:|
| ANC | ANC Monthly Facility Report | `GzO4xPVk8pl` | Monthly | 35 | 19 |
| Sick Neonate | Sick Neonate Facility Monthly Report | `ugvSAcnFoAy` | Monthly | 30 | 3 |
| Maternity | Maternity Monthly Report | `B0UtGNECmZW` | Monthly | 60 | 24 |
| KMC | Kangaroo Mother Care Monthly Reporting Form | `ACmZFToDqxh` | Monthly | 12 | 1 |

Together these forms contain 46 of the 74 unique base data elements in the supplied
MNH mapping. The remaining 28 are mainly PNC follow-up, complications, immunisation,
HIV prophylaxis, family planning, and additional newborn elements. Their authoritative
Data Entry dataset still needs to be identified.

Central Hospital Maternity HDU, Maternity Operating Theatre, and Central Hospital KMC
forms were also inspected. Their elements do not match the current workbook mappings,
so they should not be substituted for the standard Maternity and KMC forms.

## Live data retrieval evidence

### Analytics API

The three workbook IDs confirmed in the ANC visualization were retrieved across all
accessible facility-level units for all 14 months:

| Data element | Meaning | Rows | Facilities | Total |
|---|---|---:|---:|---:|
| `EVt2iC6Tn34` | ANC started in first trimester | 11,578 | 866 | 158,322 |
| `gLN6hOgR6ra` | ITN received during ANC | 10,654 | 789 | 762,683 |
| `zAvhV81SCLV` | New ANC registrations | 11,585 | 866 | 846,788 |

The request returned 33,817 valid rows across every configured period, including
3,427 explicit zeroes. Missing facility-period rows remained absent and were not
converted to zero.

### Data Value Sets API (Data Entry model)

The Data Entry retrieval pattern was verified through `/api/dataValueSets.json`:

```text
dataSet + period or startDate/endDate + orgUnit [+ children=true]
```

For Area 25 Urban Health Centre, the April 2025 ANC form returned 40 values, including
11 explicit zeroes, with completion metadata. A Lilongwe-DHO `children=true` request
for April 2025 returned 2,830 values from 72 child facilities. A single-facility date
range request returned all 14 periods successfully.

The four source forms are assigned to 788 ANC, 82 Sick Neonate, 635 Maternity, and
513 KMC facility units. Fetching them independently would require 2,018 facility-form
requests for the complete date range. District/children batching can reduce request
count but produces much larger responses and therefore requires resumable persisted
processing rather than interactive retrieval.

## Workbook conversion results

| Measure | Result |
|---|---:|
| Non-empty workbook rows processed | 52 |
| Indicators generated | 52 |
| Indicators enabled | 52 |
| Indicators requiring review | 1 |
| Indicators rejected | 0 |
| Unique atomic DHIS2 `dx` operands | 78 |
| Source worksheet | MNH indicators |
| Default range | 202504–202605 (14 months) |

The review item is **Early initiation of breastfeeding within 1 hour of birth**. Its
workbook definition is preserved as live births minus breastfeeding never/late, a
count, and is not silently converted to a percentage.

Calculated mappings implemented include Total Births as a derived sum, magnesium
sulphate coverage and antenatal corticosteroid coverage as percentages, multi-operand
sums, and the early-breastfeeding subtraction. Missing inputs and zero denominators
produce null, not zero.

## Organisation-unit status

`organisation_units.json` contains all 10,406 DHIS2 units retrieved through the
authenticated metadata API: 2 national, 27 zone, 34 district, 1,215 facility, and
9,128 community units. Native level, parent, and code metadata are retained. Exact
name/district matching produced 255 unique proposed local facility mappings; all
entries remain marked `discovered` pending governance approval.

Analytics permission testing showed that the account can query level 3, 4, and 5
selectors, but level 1 and 2 selectors return HTTP 409 because at least one unit at
each level is outside the account's data-view scope. A single April 2025 Live Births
query returned 33 district, 617 facility, and 3 community rows. Full mixed-level
publication was not attempted.

## Client and security controls

- Credentials are read from environment variables only for live sync.
- Base URL must be HTTPS and cannot embed credentials.
- TLS verification defaults to true.
- Explicit connect/read timeouts and bounded exponential retries are used.
- 400/401/403/404 are permanent typed failures; 429 and 5xx are retried within bounds.
- Analytics content type, JSON shape, required headers, row shape, numeric values, and
  duplicate dimension keys are validated.
- Logs contain counts and correlation IDs, not credentials or authorization headers.
- Imports, validation-only conversion, configuration validation, and dry run make no
  network requests.
- Runtime data and raw responses are ignored by Git.

## Storage and status

Every request can retain safe metadata, response content, row count, and SHA-256
checksum. Atomic and calculated records include sync-run and mapping versions.
Publication uses temporary files and atomic replacement. A lock prevents concurrent
syncs. Latest-attempt status is separate from last successful output, allowing a
failed attempt and retained valid data to be shown together.

## Dashboard integration

The MNH-MoH dashboard can select local validated DHIS2 output with
`scope_meta["data_source"] = "dhis2"`. It applies the current date, facility, and
district filters and displays source, last successful synchronization, latest attempt,
freshness, and mapping version. MaHIS remains the default. There is no network call
during import or rendering.

## Tests and manual checks

At the latest implementation checkpoint, 34 MNID DHIS2 tests pass using `unittest`. Coverage
includes periods/settings, workbook conversion, mapping/dependencies, organisation
units, HTTP errors/retries, response parsing, calculations, validation, query planning,
idempotency, atomic/last-known-good publication, CLI dry run, local store filters,
zero/null semantics, and no-network imports.

Manual checks performed:

- Python compilation completed successfully.
- `202504` through `202605` was confirmed as exactly 14 periods.
- Conversion accounted for every non-empty workbook row.
- Validate-only conversion completed without rewriting output.
- Complete 10,406-unit configuration validation succeeded.
- Git diffs were checked for whitespace and scope.
- Authenticated `/api/me`, organisation-unit metadata, and controlled Analytics pilot
  requests completed with TLS verification enabled.

The project environment does not include `pytest`, a formatter, linter, or type checker
configured for this package. Standard-library tests and `compileall` were therefore
used; no repository-level dependency file was modified.

## Git commits

| Commit | Purpose |
|---|---|
| `66407ad` | Assessment, architecture, package foundation, and source workbook |
| `b1a9e5e` | Settings, periods, and errors |
| `b3b7f2a` | Workbook converter, generated mapping, schema, and report |
| `221e849` | Mapping and organisation-unit validation |
| `0a7021c` | Dependency traversal correction found by tests |
| `5cf1f20` | Secure Analytics client and parser |
| `c465213` | Calculations and data validation |
| `32269d4` | Ingestion and atomic storage |
| `e5b6829` | Synchronization CLI and status |
| `05a51dd` | Local store and MNH dashboard integration |
| `6767aba` | First validated facility pilot configuration |
| `3825bd3` | Complete five-level DHIS2 hierarchy configuration |
| `0d2e4a2` | Mixed-level synchronization protection |

## Files created and modified

Created: `mnid/dhis2/` package and configuration, `mnid/data/dhis2/` ignored runtime
structure, `mnid/tests/dhis2/`, assessment, and this report.

Modified: `mnid/dashboards/MNH-MoH/layout.py` only, to add the opt-in local DHIS2
source path and source/freshness presentation.

## Known limitations and blockers

1. All DHIS2 units are present as discovered metadata, but the proposed 255 local
   facility matches still require governance approval.
2. The pilot returned 74 of 78 requested atomic rows. Missing inputs affect anaemia
   screening and MVA/retained-products, so validation correctly rejected publication.
3. Live values have not been independently reconciled with HMIS source reports.
4. Early breastfeeding calculation requires clinical confirmation.
5. Repository-level scheduler integration is outside the strict `mnid/` scope; an
   approved external scheduler must invoke the CLI.
6. Source selection is supported by renderer scope metadata, but the wider application
   does not yet expose a user-facing dropdown under this task's scope.
7. The authoritative dataset for the remaining 28 base mappings is not yet identified.
8. A resumable Data Value Set ingestion path is not yet implemented; current production
   code uses Analytics as its primary endpoint.
9. Operational alert delivery is not configured; machine-readable status is available.

## Exact operational commands

Convert workbook:

```bash
cd /home/ghost/projects/Mahis_Reports
python -m mnid.dhis2.tools.convert_indicator_workbook \
  --input "mnid/dhis2/config/source/Data Mapping - MNH dashboard - DHIS2.xlsx" \
  --output "mnid/dhis2/config/indicators.json"
```

Validate conversion only:

```bash
python -m mnid.dhis2.tools.convert_indicator_workbook \
  --input "mnid/dhis2/config/source/Data Mapping - MNH dashboard - DHIS2.xlsx" \
  --output "mnid/dhis2/config/indicators.json" --validate-only
```

Validate runtime configuration:

```bash
python -m mnid.dhis2.sync --validate-config
```

Dry run:

```bash
python -m mnid.dhis2.sync --start-period 202504 --end-period 202605 --dry-run
```

Historical backfill:

```bash
python -m mnid.dhis2.sync --start-period 202504 --end-period 202605 --backfill
```

Normal synchronization:

```bash
python -m mnid.dhis2.sync
```

## Recommended production data strategy

### Recommendation

Use a **hybrid ingestion model**:

1. Use the DHIS2 Analytics API as the primary dashboard source.
2. Use Data Value Sets as the source-form audit and reconciliation mechanism.
3. Persist both locally, but publish only validated calculated aggregates to MNID.
4. Never call either DHIS2 endpoint during dashboard rendering.

Analytics is the appropriate primary source because it retrieves multiple data
elements, periods, and organisation units efficiently and is optimized for aggregate
analysis. Data Value Sets accurately reproduce Data Entry submissions and completion
metadata but require substantially more requests and larger form-oriented responses.

### Proposed local data layers

```text
DHIS2 Analytics ----------------------+
                                      v
                              Atomic aggregate Parquet
                                      |
Data Value Sets -> form audit Parquet +--> reconciliation and validation
                                      |
                                      v
                           Calculated indicator Parquet
                                      |
                                      v
                              MNID visualization store
```

The atomic aggregate grain should be:

```text
dataset × dx × monthly period × organisation unit
```

Recommended fields include source dataset, `dx`, data element, category-option
combination, period bounds, organisation-unit ID/name/level, district, local facility
code, numeric value, explicit-zero flag, retrieval time, sync-run ID, mapping version,
and validation status.

The calculated layer should retain indicator ID/name, value, numerator, denominator,
value type, facility/district, period, source, sync time, mapping version, and validation
messages. Percentages must be recalculated as `SUM(numerator) / SUM(denominator) × 100`;
facility percentages must never be averaged directly.

### Recommended filters and visualizations

The local atomic and calculated stores will support:

- dataset/programme: ANC, Maternity, Sick Neonate, and KMC;
- reporting month and arbitrary monthly ranges;
- district and facility;
- facility level: primary, secondary, and tertiary where locally available;
- DHIS2 organisation-unit level;
- indicator, data element, and category-option combination;
- explicit zero, missing, partial, rejected, and stale states; and
- mapping version and last successful synchronization.

This structure supports KPI cards, trends, district/facility comparisons, heatmaps,
maps, rankings, completeness views, and numerator/denominator drill-down.

### Synchronization policy

- Perform a controlled historical Analytics backfill for `202504`–`202605`.
- Refresh the current and immediately previous month daily or at an agreed interval.
- Partition atomic Parquet by dataset and period.
- Publish atomically only after validation succeeds.
- Preserve last-known-good output after any failure.
- Reconcile a representative facility sample against Data Value Sets after each
  mapping release and periodically thereafter.
- Retrieve full Data Value Sets only through a resumable job with district/form
  checkpoints, bounded concurrency, and server-friendly retry/backoff.
- Never mix organisation-unit levels in one published dashboard aggregate.

### Proposed first release scope

Start with the 46 verified base elements from the four confirmed Data Entry datasets.
Do not include the remaining 28 elements until their authoritative datasets and
definitions are confirmed. This provides useful ANC, Maternity, Sick Neonate, and KMC
visualizations without silently publishing unverified mappings.

## Management decisions requested

Before continuing implementation, management/HMIS feedback is requested on:

1. Approval of Analytics as the primary visualization source and Data Value Sets as
   the audit/reconciliation source.
2. Approval to launch a controlled facility-level historical backfill for the 46
   verified elements covering April 2025 through May 2026.
3. Whether only completed Data Entry forms should be included or whether available
   values from incomplete forms may also be displayed with a warning.
4. Approval of the proposed 255 local facility matches, or nomination of an owner to
   review and correct the organisation-unit crosswalk.
5. Confirmation of the authoritative PNC dataset for the remaining mappings.
6. Clinical confirmation of the early-breastfeeding calculation.
7. Decision on the four absent pilot operands affecting anaemia screening and
   MVA/retained-products.
8. Required refresh frequency, data-retention period, and operational owner.
9. Whether users should see DHIS2 alone, MaHIS alone, or a side-by-side reconciliation
   view when both sources are available.

## Recommended next steps

1. Obtain management decisions on the nine items above.
2. Identify and validate the PNC dataset for the remaining 28 base elements.
3. Review the crosswalk, missing operands, and calculated-indicator definitions.
4. Add dataset ownership metadata to the 46 verified mappings.
5. Implement partitioned atomic Analytics storage and a resumable Data Value Set
   reconciliation job.
6. Backfill one approved district, reconcile it against Data Entry forms, and obtain
   data-quality sign-off.
7. Expand to the approved facility-level scope and 14-month range.
8. Connect dataset, period, district, facility, facility-level, and validation filters
   to the MNH visualizations.
9. Configure external scheduling, monitoring, alerting, secret rotation, and support
   ownership before production handover.
