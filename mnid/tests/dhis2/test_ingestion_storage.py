"""Query planning, atomic publication, and last-known-good tests."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from mnid.dhis2.ingestion import build_query_plan, run_ingestion
from mnid.dhis2.settings import DHIS2Settings


def op(dx): return {"dx": dx, "data_element_id": dx, "category_option_combo_id": None, "type": "data_element"}


class FakeClient:
    payload = None
    def __init__(self, settings): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def analytics(self, dx, periods, org_units, **_): return self.payload


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.settings = DHIS2Settings.from_env({
            "MNH_DHIS2_USERNAME": "u", "MNH_DHIS2_PASSWORD": "p",
            "MNH_DHIS2_RAW_DATA_DIR": str(root / "raw"),
            "MNH_DHIS2_NORMALIZED_DATA_DIR": str(root / "normalized"),
            "MNH_DHIS2_AGGREGATE_DATA_DIR": str(root / "aggregate"),
            "MNH_DHIS2_STATUS_DIR": str(root / "status"),
            "MNH_DHIS2_DX_BATCH_SIZE": "1", "MNH_DHIS2_PERIOD_BATCH_SIZE": "1",
        }, require_credentials=True)
        self.mapping = {"mapping_version": "test", "indicators": [{
            "id": "births", "name": "Births", "enabled": True, "value_type": "count",
            "calculation": {"operation": "direct", "operands": [op("A2345678901")]},
        }]}
        self.units = [{"org_unit_id": "O2345678901", "name": "Pilot", "district": "D", "local_facility_code": "F", "enabled": True}]

    def tearDown(self): self.temp.cleanup()

    def test_plan_is_batched_and_deterministic(self):
        plan = build_query_plan(self.mapping, self.units, ["202504", "202505"], self.settings)
        self.assertEqual(2, len(plan)); self.assertEqual("request-0001", plan[0].request_id)

    def test_complete_sync_publishes_and_repeat_is_duplicate_safe(self):
        FakeClient.payload = {"headers": [{"name": x} for x in ("dx", "pe", "ou", "value")], "rows": [["A2345678901", "202504", "O2345678901", "0"]]}
        status = run_ingestion(self.settings, self.mapping, self.units, ["202504"], client_factory=FakeClient)
        self.assertTrue(status["published"])
        path = self.settings.aggregate_data_dir / "current.parquet"
        self.assertEqual(0, pd.read_parquet(path).iloc[0]["value"])
        run_ingestion(self.settings, self.mapping, self.units, ["202504"], client_factory=FakeClient)
        self.assertEqual(1, len(pd.read_parquet(path)))

    def test_failed_validation_retains_last_known_good(self):
        FakeClient.payload = {"headers": [{"name": x} for x in ("dx", "pe", "ou", "value")], "rows": [["A2345678901", "202504", "O2345678901", "1"]]}
        run_ingestion(self.settings, self.mapping, self.units, ["202504"], client_factory=FakeClient)
        path = self.settings.aggregate_data_dir / "current.parquet"; before = path.read_bytes()
        FakeClient.payload = {"headers": [{"name": x} for x in ("dx", "pe", "ou", "value")], "rows": [["A2345678901", "202504", "O2345678901", "bad"]]}
        with self.assertRaises(Exception):
            run_ingestion(self.settings, self.mapping, self.units, ["202504"], client_factory=FakeClient)
        self.assertEqual(before, path.read_bytes())


if __name__ == "__main__": unittest.main()
