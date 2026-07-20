# DHIS2 mapping configuration

`indicators.json` is generated from the source workbook and validated before use.
Do not edit generated source references or calculation operands casually; regenerate
with the converter and review the conversion report.

`organisation_units.json` currently contains one explicitly enabled pilot facility,
Area 25 Urban Health Centre. Its DHIS2 level, parent, code, and confirmed local match
are preserved for audit. Entries marked `pilot` must be reviewed before a production
rollout; use `approved` only after governance sign-off. Never copy the hard-coded
organisation unit from the legacy shared DHIS2 prototype.
