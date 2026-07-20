# DHIS2 mapping configuration

`indicators.json` is generated from the source workbook and validated before use.
Do not edit generated source references or calculation operands casually; regenerate
with the converter and review the conversion report.

`organisation_units.json` is intentionally empty because no approved DHIS2-to-MaHIS
crosswalk was supplied. Add reviewed entries matching the adjacent JSON Schema.
Live synchronization refuses to run until at least one unit is enabled. Never copy
the hard-coded organisation unit from the legacy shared DHIS2 prototype.
