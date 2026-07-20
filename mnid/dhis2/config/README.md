# DHIS2 mapping configuration

`indicators.json` is generated from the source workbook and validated before use.
Do not edit generated source references or calculation operands casually; regenerate
with the converter and review the conversion report.

`organisation_units.json` contains the complete DHIS2 hierarchy retrieved on
20 July 2026: national, zone, district, facility, and community levels. Native level,
parent, code, and discovered local facility matches are preserved. Entries marked
`discovered` require governance review; use `approved` only after sign-off. Select a
single level with `--org-level` during synchronization to avoid mixing parent
aggregates with child records. Never copy the hard-coded organisation unit from the
legacy shared DHIS2 prototype.
