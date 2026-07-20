"""Semantic mapping validation tests."""

import copy
import json
import unittest
from pathlib import Path

from mnid.dhis2.exceptions import DHIS2MappingError
from mnid.dhis2.mappings import atomic_dx_values, dependency_order, load_indicator_mapping
from mnid.dhis2.schemas import validate_indicator_mapping, validate_organisation_units


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path("mnid/dhis2/config/indicators.json")
        cls.mapping = json.loads(path.read_text(encoding="utf-8"))

    def test_generated_mapping_is_valid_and_ordered(self):
        validated = validate_indicator_mapping(copy.deepcopy(self.mapping))
        self.assertEqual(78, len(atomic_dx_values(validated)))
        ids = [item["id"] for item in dependency_order(validated)]
        self.assertLess(ids.index("live_births"), ids.index("total_births"))

    def test_unknown_and_circular_dependencies_fail(self):
        mapping = copy.deepcopy(self.mapping)
        total = next(item for item in mapping["indicators"] if item["id"] == "total_births")
        total["calculation"]["indicator_ids"] = ["unknown"]
        with self.assertRaises(DHIS2MappingError):
            validate_indicator_mapping(mapping)
        circular = copy.deepcopy(self.mapping)
        live = next(item for item in circular["indicators"] if item["id"] == "live_births")
        live["calculation"] = {"operation": "sum_indicators", "indicator_ids": ["total_births"]}
        with self.assertRaises(DHIS2MappingError):
            validate_indicator_mapping(circular)

    def test_duplicate_operand_fails(self):
        mapping = copy.deepcopy(self.mapping)
        live = next(item for item in mapping["indicators"] if item["id"] == "live_births")
        live["calculation"]["operands"].append(copy.deepcopy(live["calculation"]["operands"][0]))
        with self.assertRaises(DHIS2MappingError):
            validate_indicator_mapping(mapping)

    def test_org_units_empty_allowed_for_config_but_not_live(self):
        empty = {"schema_version": "1.0", "organisation_units": []}
        validate_organisation_units(empty)
        with self.assertRaises(DHIS2MappingError):
            validate_organisation_units(empty, require_enabled=True)

    def test_valid_org_unit_and_duplicate_detection(self):
        unit = {
            "org_unit_id": "Abc12345678", "name": "Pilot", "level": "facility",
            "district": "Pilot District", "local_facility_code": "P01",
            "active_from": "2025-04", "active_to": None, "enabled": True,
        }
        validate_organisation_units({"schema_version": "1.0", "organisation_units": [unit]})
        with self.assertRaises(DHIS2MappingError):
            validate_organisation_units({"schema_version": "1.0", "organisation_units": [unit, unit]})


if __name__ == "__main__":
    unittest.main()
