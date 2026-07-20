# HMIS Dashboard vs Live DHIS2 Validation

Validation date: 2026-07-20  
Reporting period: January 2026–May 2026  
DHIS2 scope: accessible facility-level organisation units (`LEVEL-4`)

## Result

The cached MNH HMIS dashboard snapshot matches a fresh read-only DHIS2 Analytics pull
for all 25 indicators.

| Validation measure | Result |
|---|---:|
| DHIS2 atomic operands queried | 36 |
| Dashboard indicators compared | 25 |
| Cached calculated rows | 84,205 |
| Fresh live calculated rows | 84,205 |
| Cached reporting units | 861 |
| Live reporting units | 861 |
| Five-month totals matching | 25 of 25 |
| May 2026 figures matching | 25 of 25 |
| Indicators with differences | 0 |

The comparison was read-only and did not overwrite `hmis_test.parquet`. The detailed
machine-readable comparison is stored locally at:

```text
mnid/data/dhis2/normalized/comparisons/hmis_202601_202605_058a1684.csv
```

This CSV is runtime validation data and is excluded from Git.

## Indicator comparison

| Domain | Indicator | Dashboard Jan–May | Live DHIS2 Jan–May | Dashboard May | Live DHIS2 May | Result |
|---|---|---:|---:|---:|---:|---|
| Antenatal care | ANC Visits | 300,991 | 300,991 | 58,352 | 58,352 | Match |
| Antenatal care | At least 4 ANC contacts | 129,289 | 129,289 | 25,301 | 25,301 | Match |
| Antenatal care | Blood pressure measured | 4,767 | 4,767 | 1,224 | 1,224 | Match |
| Antenatal care | New ANC registrations | 318,090 | 318,090 | 61,400 | 61,400 | Match |
| Antenatal care | Received 120+ FeFo tablets | 93,661 | 93,661 | 19,598 | 19,598 | Match |
| Antenatal care | Received ITN during ANC | 277,327 | 277,327 | 53,776 | 53,776 | Match |
| Antenatal care | Screened for syphilis | 279,594 | 279,594 | 51,485 | 51,485 | Match |
| Antenatal care | Started ANC in first trimester (0-12 weeks) | 60,738 | 60,738 | 11,546 | 11,546 | Match |
| Antenatal care | Tested for HIV | 288,351 | 288,351 | 55,492 | 55,492 | Match |
| Antenatal care | Tetanus doses (2+) | 132,810 | 132,810 | 28,874 | 28,874 | Match |
| Births and outcomes | Fresh Stillbirths | 2,021 | 2,021 | 430 | 430 | Match |
| Births and outcomes | Live Births | 252,206 | 252,206 | 52,401 | 52,401 | Match |
| Births and outcomes | Macerated Stillbirths | 2,155 | 2,155 | 490 | 490 | Match |
| Births and outcomes | Maternal Deaths | 80 | 80 | 18 | 18 | Match |
| Births and outcomes | Neonatal Deaths | 2,540 | 2,540 | 463 | 463 | Match |
| Births and outcomes | Stillbirths | 4,114 | 4,114 | 899 | 899 | Match |
| Births and outcomes | Total Births | 256,030 | 256,030 | 53,192 | 53,192 | Match |
| Delivery and newborn care | Delivered at home or in transit | 5,882 | 5,882 | 1,123 | 1,123 | Match |
| Delivery and newborn care | Delivered at this facility | 247,319 | 247,319 | 51,722 | 51,722 | Match |
| Delivery and newborn care | Delivered by skilled attendant | 243,982 | 243,982 | 51,112 | 51,112 | Match |
| Delivery and newborn care | Facility deliveries | 247,589 | 247,589 | 51,760 | 51,760 | Match |
| Delivery and newborn care | Newborns not breathing at birth receiving bag-mask ventilation | 3,935 | 3,935 | 732 | 732 | Match |
| Delivery and newborn care | Normal vaginal delivery | 225,886 | 225,886 | 46,993 | 46,993 | Match |
| Delivery and newborn care | Uterotonic given after birth | 249,277 | 249,277 | 51,935 | 51,935 | Match |
| Delivery and newborn care | Vitamin K at birth | 41,422 | 41,422 | 10,836 | 10,836 | Match |

## Headline figure verification

The seven figures shown in the dashboard summary were confirmed exactly:

| Indicator | Dashboard May | Live DHIS2 May | Dashboard Jan–May | Live DHIS2 Jan–May |
|---|---:|---:|---:|---:|
| Total Births | 53,192 | 53,192 | 256,030 | 256,030 |
| Live Births | 52,401 | 52,401 | 252,206 | 252,206 |
| Stillbirths | 899 | 899 | 4,114 | 4,114 |
| Fresh Stillbirths | 430 | 430 | 2,021 | 2,021 |
| Macerated Stillbirths | 490 | 490 | 2,155 | 2,155 |
| Maternal Deaths | 18 | 18 | 80 | 80 |
| Neonatal Deaths | 463 | 463 | 2,540 | 2,540 |

## Method

1. Loaded the same reviewed 25-indicator subset used by the dashboard.
2. Resolved its 36 unique atomic DHIS2 operands.
3. Queried live DHIS2 Analytics for `202601`–`202605` and `LEVEL-4` in two bounded
   requests.
4. Parsed and validated the returned headers and numeric rows.
5. Applied the same dependency ordering, sums, and missing-input rules used by the
   dashboard synchronization process.
6. Aggregated both cached and freshly calculated data by indicator for the entire
   five-month window and separately for May 2026.
7. Compared values with exact numeric equality and compared reporting-unit coverage.

## Interpretation and data-quality follow-up

This result confirms that the dashboard faithfully represents a fresh DHIS2 Analytics
response under the same scope and calculation rules. It is a technical source
reconciliation; it does not replace HMIS programme review or comparison with signed
facility source registers.

### Derived-total completeness

The calculation engine treats a missing component as missing, not zero. A derived
facility-month total is published only when all required components exist. Therefore,
aggregate arithmetic can differ when facilities omit one component:

- May Fresh + Macerated Stillbirths is `430 + 490 = 920`, while paired-complete
  Stillbirths is `899` (difference `21`).
- January–May Fresh + Macerated Stillbirths is `2,021 + 2,155 = 4,176`, while
  paired-complete Stillbirths is `4,114` (difference `62`).
- May Live Births + Stillbirths is `52,401 + 899 = 53,300`, while paired-complete
  Total Births is `53,192` (difference `108`).
- January–May Live Births + Stillbirths is `252,206 + 4,114 = 256,320`, while
  paired-complete Total Births is `256,030` (difference `290`).

This behavior prevents absent reports from being silently interpreted as zero, but the
HMIS team should decide whether national summary totals should instead sum independently
available components and carry a completeness warning.

### Reporting coverage

Most headline birth indicators contain values from approximately 638–639 reporting
units during the selected window. Neonatal Deaths contains values from only 73 units.
That may reflect assignment of the Sick Neonate dataset, permissions, or reporting
coverage, and should be reviewed before treating the neonatal death total as nationally
complete. Low-volume or unexpectedly sparse measures, including Blood pressure
measured, should also be reconciled with the relevant Data Entry form and reporting
completion metadata.

## Conclusion

The dashboard implementation passed the live DHIS2 technical reconciliation for
January–May 2026 with zero numerical differences across all 25 indicators. Production
interpretation still requires review of component completeness, dataset assignment,
and facility reporting coverage.

