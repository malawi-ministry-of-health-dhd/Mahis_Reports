# MNID/MNH DHIS2 Implementation Assessment

Date: 2026-07-20

## Scope

This implementation is isolated to `mnid/`. Existing HMIS reports and shared DHIS2,
database extraction, scheduler, and application configuration code are not changed.

## Files and behaviour inspected

- `mnid/aggregation/engine.py`: reads local MaHIS/OpenMRS-derived Parquet rows,
  calculates configured indicators, and publishes aggregate Parquet output.
- `mnid/aggregation/store.py`: caches aggregate Parquet per route and applies period,
  facility, and district filters.
- `mnid/aggregation/scheduler.py`: protects aggregate builds with a lock and records
  status, but is invoked by a scheduler outside this task's allowed scope.
- `mnid/views/renderer.py`, `kpi_engine.py`, `trends.py`, and `callbacks.py`: load
  local data, resolve route/facility/district scope, and prefer cached aggregates.
- `mnid/core/constants.py` and `cache.py`: maintain route-scoped facility metadata
  and dashboard caches.
- `mnid/dashboards/MNH-MoH/layout.py`: consumes current local MNID data and
  aggregates; it has no explicit data-source selector.
- `helpers/dhis_integrater.py`, `helpers/reports_class.py`, and
  `helpers/date_ranges.py`: a shared prototype supports Basic Authentication,
  data-value retrieval, mapping, and period formatting but disables TLS, has weak
  errors, and includes a hard-coded organisation unit. It will not be reused.
- `data_storage.py` and `db_services.py`: populate the current local Parquet source.
- Root tests and dependencies: the environment contains requests, pandas, pyarrow,
  and openpyxl. `jsonschema` and `pytest` are not installed in the project virtual
  environment, so validation will use a dependency-free schema/application validator
  and tests will use Python's standard `unittest` framework.

## Current data flow

```text
MaHIS/OpenMRS MySQL -> data_storage -> route Parquet -> MNID aggregation
-> aggregate Parquet/cache -> dashboard callbacks
```

Filters are applied to `Facility_CODE`, `District`, date windows, route, indicator,
and grain in the views and aggregate-store query functions. There is no current
DHIS2 source and no network request is made by MNID.

## Reusable concepts

- Local Parquet publication and in-memory cache pattern.
- Route/facility/district filtering contracts.
- Aggregation lock and status metadata pattern.
- Python logging conventions.
- `requests`, `openpyxl`, pandas, and pyarrow already available.

## Limitations to address

- No secure MNID-local DHIS2 client, mapping registry, organisation-unit crosswalk,
  query planner, validation, audit storage, sync status, or CLI.
- No source-aware MNID store.
- No approved organisation-unit configuration was supplied.
- The workbook exists and contains mappings, but formulas and identifiers require
  deterministic conversion and validation.
- Root scheduling cannot be modified in this scope; sync will be explicitly
  invokable and documented for an external scheduler.

## Proposed architecture

```text
Explicit/scheduled sync -> secure Analytics API client -> raw audit snapshots
-> header-driven normalization -> deterministic calculations and validation
-> atomic last-known-good Parquet publication -> DHIS2 store adapter -> MNH UI
```

Dashboard imports and rendering will never call DHIS2. A failed or partial sync will
record status and preserve the previous validated output.

## Planned files

- `mnid/dhis2/`: settings, periods, exceptions, schemas, mappings, client,
  calculations, validation, storage, ingestion, status, sync CLI, documentation.
- `mnid/dhis2/config/`: deterministic mapping JSON and schemas, conversion report,
  organisation-unit placeholder, and source workbook.
- `mnid/dhis2/tools/convert_indicator_workbook.py`: offline Excel converter.
- `mnid/tests/dhis2/`: standard-library automated tests with mocked HTTP and
  generated workbooks.
- `mnid/dhis2_store.py` or an equivalent adapter and a minimal MNH layout change.
- `mnid/DHIS2_IMPLEMENTATION_REPORT.md`: final evidence and operational guide.

## Risks

- Incorrect formula interpretation or facility crosswalk can misattribute values.
- Missing organisation units blocks live synchronization.
- Upstream metadata changes can invalidate approved mappings.
- DHIS2 availability and throttling can interrupt ingestion.
- Directly replacing existing MNID data could break established dashboards;
  therefore DHIS2 remains opt-in and separately stored.

## Known blockers

- No approved DHIS2 organisation-unit IDs/local facility crosswalk is present.
- No credentials or authenticated test environment were provided.
- Clinical approval is required for mappings classified as `review_required`.
- Integration with the repository-level scheduler is excluded by the strict scope.

## Implementation sequence

1. Add settings, periods, exceptions, and tests.
2. Convert and validate workbook mappings.
3. Add mapping and organisation-unit validation.
4. Add secure Analytics API client and parser.
5. Add calculations and data validation.
6. Add query planning, ingestion, audit, atomic storage, and status.
7. Add sync CLI and dry run.
8. Add a backward-compatible local DHIS2 store and MNH source/status UI.
9. Complete tests, runbook, implementation report, and security review.
