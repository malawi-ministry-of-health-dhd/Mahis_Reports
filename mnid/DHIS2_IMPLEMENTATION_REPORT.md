# MNID/MNH DHIS2 Integration Implementation Report

Date: 2026-07-20

## Executive summary

A secure, offline-first DHIS2 Analytics integration has been implemented under
`mnid/`. It converts the supplied mapping workbook into deterministic validated JSON,
plans and executes bounded Analytics queries, preserves audit data, normalizes and
calculates MNH indicators, validates completeness, atomically publishes Parquet, and
provides an opt-in local data source for the MNH-MoH dashboard.

No live API request was made. Production synchronization remains deliberately blocked
because no approved organisation-unit crosswalk was supplied. Current MaHIS/OpenMRS
dashboard behaviour remains the default and is not replaced.

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

`organisation_units.json` is present, schema-controlled, and intentionally empty.
No organisation-unit IDs were invented or copied from legacy code. Validation allows
the package to import and tests to run, but configuration validation, dry run, and live
sync fail clearly until at least one approved unit is enabled.

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

At implementation completion, 33 MNID DHIS2 tests pass using `unittest`. Coverage
includes periods/settings, workbook conversion, mapping/dependencies, organisation
units, HTTP errors/retries, response parsing, calculations, validation, query planning,
idempotency, atomic/last-known-good publication, CLI dry run, local store filters,
zero/null semantics, and no-network imports.

Manual checks performed:

- Python compilation completed successfully.
- `202504` through `202605` was confirmed as exactly 14 periods.
- Conversion accounted for every non-empty workbook row.
- Validate-only conversion completed without rewriting output.
- Real configuration validation produced the expected missing-org-unit blocker.
- Git diffs were checked for whitespace and scope.
- No authenticated live request was attempted.

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

## Files created and modified

Created: `mnid/dhis2/` package and configuration, `mnid/data/dhis2/` ignored runtime
structure, `mnid/tests/dhis2/`, assessment, and this report.

Modified: `mnid/dashboards/MNH-MoH/layout.py` only, to add the opt-in local DHIS2
source path and source/freshness presentation.

## Known limitations and blockers

1. Approved organisation-unit and facility-code mappings are missing.
2. Credentials, permissions, network path, and TLS chain have not been validated.
3. No live values have been independently reconciled with HMIS source reports.
4. Early breastfeeding calculation requires clinical confirmation.
5. Repository-level scheduler integration is outside the strict `mnid/` scope; an
   approved external scheduler must invoke the CLI.
6. Source selection is supported by renderer scope metadata, but the wider application
   does not yet expose a user-facing dropdown under this task's scope.
7. Operational alert delivery is not configured; machine-readable status is available.

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

## Recommended next steps

1. Obtain and dual-review the official organisation-unit/facility crosswalk.
2. Approve the ambiguous early-breastfeeding definition.
3. Provision a read-only DHIS2 service account and environment-managed secrets.
4. Validate TLS/network access without weakening certificate checks.
5. Run a one-unit, one-period, small-`dx` pilot and independently reconcile values.
6. Expand gradually to 14 periods after pilot sign-off.
7. Configure external scheduling, status monitoring, and alert ownership.
8. Add a user-facing source selector only after governance approves how MaHIS and
   DHIS2 sources should be presented or compared.
