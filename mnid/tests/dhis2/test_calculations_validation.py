"""Calculation and publishability tests."""

import unittest
from decimal import Decimal

from mnid.dhis2.calculations import calculate_indicators
from mnid.dhis2.client import AnalyticsValue
from mnid.dhis2.validation import validate_sync_data


def op(dx):
    return {"type": "data_element", "dx": dx, "data_element_id": dx, "category_option_combo_id": None}


class CalculationTests(unittest.TestCase):
    def mapping(self):
        return {
            "schema_version": "1.0", "mapping_version": "test",
            "reporting_period": {"start_period": "202504", "end_period": "202504"},
            "indicators": [
                {"id": "a", "name": "A", "enabled": True, "value_type": "count", "validation": {"status": "valid"}, "calculation": {"operation": "direct", "operands": [op("A2345678901")] }},
                {"id": "b", "name": "B", "enabled": True, "value_type": "count", "validation": {"status": "valid"}, "calculation": {"operation": "sum", "operands": [op("B2345678901"), op("C2345678901")] }},
                {"id": "total", "name": "Total", "enabled": True, "value_type": "count", "validation": {"status": "valid"}, "calculation": {"operation": "sum_indicators", "indicator_ids": ["a", "b"]}},
                {"id": "pct", "name": "Pct", "enabled": True, "value_type": "percentage", "validation": {"status": "valid"}, "calculation": {"operation": "percentage", "multiplier": 100, "numerator": {"operands": [op("A2345678901")]}, "denominator": {"operands": [op("D2345678901")]}}},
            ],
        }

    def test_direct_sum_percentage_and_derived(self):
        atomic = {
            ("A2345678901", "202504", "O2345678901"): Decimal("2"),
            ("B2345678901", "202504", "O2345678901"): Decimal("3"),
            ("C2345678901", "202504", "O2345678901"): Decimal("4"),
            ("D2345678901", "202504", "O2345678901"): Decimal("4"),
        }
        rows = calculate_indicators(self.mapping(), atomic, ["202504"], [{"org_unit_id": "O2345678901"}])
        values = {row["indicator_id"]: row["value"] for row in rows}
        self.assertEqual(Decimal("2"), values["a"])
        self.assertEqual(Decimal("7"), values["b"])
        self.assertEqual(Decimal("9"), values["total"])
        self.assertEqual(Decimal("50.0"), values["pct"])

    def test_missing_and_zero_denominator_are_null(self):
        mapping = self.mapping()
        atomic = {("A2345678901", "202504", "O2345678901"): Decimal("2"), ("D2345678901", "202504", "O2345678901"): Decimal("0")}
        rows = calculate_indicators(mapping, atomic, ["202504"], [{"org_unit_id": "O2345678901"}])
        values = {row["indicator_id"]: row for row in rows}
        self.assertIsNone(values["b"]["value"])
        self.assertIsNone(values["pct"]["value"])
        self.assertEqual("partial", values["pct"]["validation_status"])

    def test_validation_rejects_partial_completion(self):
        mapping = self.mapping()
        report = validate_sync_data(mapping, [], [], ["202504"], [{"org_unit_id": "O2345678901"}], completed_requests=0, planned_requests=1)
        self.assertFalse(report["publishable"])
        self.assertEqual("rejected", report["status"])

    def test_explicit_zero_is_preserved(self):
        row = AnalyticsValue("A2345678901", "202504", "O2345678901", Decimal("0"), "0")
        rows = calculate_indicators(self.mapping(), {(row.dx, row.period, row.org_unit_id): row.value}, ["202504"], [{"org_unit_id": "O2345678901"}])
        a = next(item for item in rows if item["indicator_id"] == "a")
        self.assertEqual(Decimal("0"), a["value"])


if __name__ == "__main__":
    unittest.main()
