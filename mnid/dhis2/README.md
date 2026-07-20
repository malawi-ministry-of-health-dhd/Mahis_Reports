# MNID/MNH DHIS2 integration

## Purpose and scope

This package retrieves approved aggregate Maternal and Newborn Health values from
the Malawi HMIS DHIS2 Analytics API and publishes validated local data for MNH
dashboards. It is isolated under `mnid/` and does not alter legacy HMIS reports.

Dashboards never query DHIS2. Only `python -m mnid.dhis2.sync` performs network I/O.
This keeps rendering fast, provides an audit trail, and retains the last validated
dataset when DHIS2, configuration, parsing, or validation fails.

## Architecture

```text
Mapping workbook -> offline converter -> validated indicators.json
                                              |
DHIS2 Analytics -> secure batched client -> raw audit snapshots
                                              |
                                     normalized atomic values
                                              |
                                  calculated/validated indicators
                                              |
                               atomic last-known-good Parquet
                                              |
                                  MNID DHIS2 store -> MNH-MoH UI
```

Runtime data is stored below `mnid/data/dhis2/` and ignored by Git:

- `raw/<sync-run-id>/`: safe request metadata and raw JSON responses;
- `normalized/<sync-run-id>/`: normalized atomic Parquet and validation report;
- `aggregates/current.parquet`: last validated calculated indicators;
- `aggregates/current_metadata.json`: published mapping and freshness metadata; and
- `status/current.json`: latest synchronization attempt.

## Environment variables

```env
MNH_DHIS2_BASE_URL=https://dhis2.health.gov.mw
MNH_DHIS2_USERNAME=
MNH_DHIS2_PASSWORD=
MNH_DHIS2_START_PERIOD=202504
MNH_DHIS2_END_PERIOD=202605
MNH_DHIS2_CONNECT_TIMEOUT_SECONDS=10
MNH_DHIS2_READ_TIMEOUT_SECONDS=60
MNH_DHIS2_MAX_RETRIES=3
MNH_DHIS2_VERIFY_TLS=true
MNH_DHIS2_DX_BATCH_SIZE=30
MNH_DHIS2_ORG_UNIT_BATCH_SIZE=10
MNH_DHIS2_PERIOD_BATCH_SIZE=14
MNH_DHIS2_RAW_DATA_DIR=
MNH_DHIS2_NORMALIZED_DATA_DIR=
MNH_DHIS2_AGGREGATE_DATA_DIR=
MNH_DHIS2_STATUS_DIR=
MNH_DHIS2_STALE_AFTER_HOURS=48
```

Credentials must be injected by the deployment environment or secrets manager and
must belong to a least-privilege read-only service account. Do not put credentials
in JSON, source files, command arguments, logs, or shell history. TLS verification
defaults to enabled and must not be disabled to bypass certificate errors.

Imports and dry runs do not require credentials. Live synchronization does.

## Indicator workbook and conversion

The source workbook is stored at:

```text
mnid/dhis2/config/source/Data Mapping - MNH dashboard - DHIS2.xlsx
```

Runtime synchronization reads JSON, never Excel. Convert the workbook with:

```bash
cd /home/ghost/projects/Mahis_Reports

python -m mnid.dhis2.tools.convert_indicator_workbook \
  --input "mnid/dhis2/config/source/Data Mapping - MNH dashboard - DHIS2.xlsx" \
  --output "mnid/dhis2/config/indicators.json"
```

Validate conversion without changing files:

```bash
python -m mnid.dhis2.tools.convert_indicator_workbook \
  --input "mnid/dhis2/config/source/Data Mapping - MNH dashboard - DHIS2.xlsx" \
  --output "mnid/dhis2/config/indicators.json" \
  --validate-only
```

Useful options are `--sheet`, `--mapping-version`, `--report-output`, `--strict`,
`--overwrite`, and `--validate-only`. Output is deterministic and atomically replaced
only after successful conversion. Removed indicators are retained but disabled.

The converter supports direct operands, sums, data-element/category-combination
operands, percentages, subtraction, and sums of derived indicators. Formula text is
never sent to DHIS2. Every non-empty row is retained and classified as `valid`,
`review_required`, or `rejected`. Review `indicator_conversion_report.json` after
every regeneration and obtain clinical approval for ambiguous calculations.

## Organisation-unit configuration

`config/organisation_units.json` contains the discovered DHIS2 hierarchy and proposed
local crosswalk. Discovered mappings are not equivalent to governance approval.
Example shape:

```json
{
    "schema_version": "1.0",
    "organisation_units": [
        {
            "org_unit_id": "Approved11Id",
            "name": "Example Facility",
            "level": "facility",
            "district": "Example District",
            "local_facility_code": "LOCAL-CODE",
            "active_from": "2025-04",
            "active_to": null,
            "enabled": true
        }
    ]
}
```

Use real approved DHIS2 UIDs; the example is structural only. Validation rejects
invalid/duplicate IDs, duplicate active local mappings, bad levels, invalid dates,
and reversed active ranges. Live sync is blocked when no unit is enabled.

## Configuration validation and dry run

```bash
python -m mnid.dhis2.sync --validate-config
```

```bash
python -m mnid.dhis2.sync \
  --start-period 202504 \
  --end-period 202605 \
  --dry-run
```

Dry run validates configuration, resolves 14 inclusive monthly periods, deduplicates
atomic `dx` values, and reports the deterministic batch/request count. It performs no
network request, does not require credentials, and does not update sync status.

## Synchronization and historical backfill

```bash
python -m mnid.dhis2.sync
```

```bash
python -m mnid.dhis2.sync \
  --start-period 202504 \
  --end-period 202605 \
  --backfill
```

Use repeated `--org-unit DHIS2_UID` options for a controlled pilot. Begin with one
organisation unit, one period, and a small `MNH_DHIS2_DX_BATCH_SIZE`. Validate the
result independently before expanding. `--backfill` documents operator intent; the
same idempotent pipeline is used, so a repeat replaces rather than duplicates the
published snapshot.

The package does not modify the repository-level scheduler. Production operations
must schedule the command externally after approval.

## Dashboard source behaviour

The existing MaHIS/OpenMRS source remains the default. The MNH-MoH renderer uses
DHIS2 only when its scope metadata contains:

```python
{"data_source": "dhis2"}
```

It then reads `aggregates/current.parquet`, applies the current date/facility/district
scope, and shows source, mapping version, latest attempt, last successful sync, and
freshness. Zero remains a numeric zero; missing data remains null/unavailable. A
failed latest attempt does not remove the previously validated dashboard data.

## Adding or changing indicators

1. Save the reviewed workbook at the documented source path.
2. Run `--validate-only` and inspect classifications.
3. Run the converter and inspect the Git diff and conversion report.
4. Resolve invalid UIDs, unknown dependencies, circular references, and unexpected
   formula changes.
5. Obtain clinical/HMIS approval for `review_required` rows.
6. Run all tests and a dry run before synchronization.

Do not hand-build API `dx` values from formula prose or silently reinterpret a count
as a percentage.

## Testing

The integration uses standard-library `unittest` because `pytest` is not installed in
the repository environment:

```bash
venv/bin/python -m unittest discover -s mnid/tests/dhis2 -p 'test_*.py' -v
venv/bin/python -m compileall -q mnid/dhis2 mnid/dashboards/MNH-MoH/layout.py
```

Tests use generated workbooks, temporary storage, mocked HTTP, and fake clients. They
do not require or contact live DHIS2.

## Troubleshooting

- **No enabled organisation units:** obtain and configure the approved crosswalk.
- **Credentials missing:** inject both username and password for live sync.
- **TLS failure:** install/repair the approved CA chain; do not disable verification.
- **401/403:** verify the service account and Analytics read permissions.
- **429/5xx/timeouts:** bounded retries occur automatically; inspect status and audit.
- **Validation failed:** inspect the run's normalized validation report. Current
  dashboard data remains unchanged.
- **Dashboard says unavailable:** verify `current.parquet`, date/filter scope, and
  `status/current.json` without triggering a network request.
- **Stale data:** inspect the latest failed attempt and rerun only after correcting it.

## Operational ownership and limitations

HMIS owns source metadata and organisation-unit approval; MNID owns dashboard meaning;
data-quality owners approve reconciliation; infrastructure owns secrets, certificates,
scheduling, and alerts. The complete DHIS2 hierarchy is configured as discovered
metadata; governance review of the proposed crosswalk is still required.
Authentication, TLS, and one-period Analytics retrieval have been verified. Clinical
review of early breastfeeding and two incomplete pilot mappings remains necessary.

## Pilot result: 20 July 2026

Area 25 Urban Health Centre was matched by exact normalized name to local code
`LL040037` and configured with its DHIS2 level-4 metadata. A one-period (`202504`)
Analytics test requested all 78 atomic operands in three batches:

- all three requests completed;
- 74 atomic rows were returned;
- no returned rows were malformed, duplicated, unknown, or outside scope;
- four requested `dx` rows were absent; and
- two calculated indicators were consequently incomplete.

The missing inputs affect **Screened for anaemia** and **Signal: MVA / retained
products**. The validation gate rejected publication, correctly preserving the rule
that an absent DHIS2 row is not a numeric zero. HMIS should confirm whether those
operands are inactive, unavailable for this facility/period, or require revised
mappings before the first dataset is published.
