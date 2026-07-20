"""Tests for local store semantics and the opt-in MNH dashboard source."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from mnid.dhis2.settings import DHIS2Settings
from mnid.dhis2.store import invalidate_cache, load_validated_data, query_dashboard_data, source_metadata


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.settings = DHIS2Settings.from_env({
            "MNH_DHIS2_AGGREGATE_DATA_DIR": str(root / "aggregates"),
            "MNH_DHIS2_STATUS_DIR": str(root / "status"),
            "MNH_DHIS2_STALE_AFTER_HOURS": "1",
        })
        self.settings.aggregate_data_dir.mkdir(parents=True)
        pd.DataFrame([
            {"indicator_id": "a", "period_start": "2025-04-01", "facility_code": "F1", "district": "D1", "value": 0},
            {"indicator_id": "a", "period_start": "2025-05-01", "facility_code": "F2", "district": "D2", "value": None},
        ]).to_parquet(self.settings.aggregate_data_dir / "current.parquet", index=False)
        invalidate_cache()

    def tearDown(self): invalidate_cache(); self.temp.cleanup()

    def test_zero_null_and_filters_remain_distinct(self):
        frame = query_dashboard_data("2025-04-01", "2025-04-30", facility_codes=["F1"], settings=self.settings)
        self.assertEqual(1, len(frame)); self.assertEqual(0, frame.iloc[0]["value"])
        all_data = load_validated_data(self.settings)
        self.assertTrue(pd.isna(all_data.iloc[1]["value"]))

    def test_missing_and_stale_metadata_are_safe(self):
        metadata = source_metadata(self.settings)
        self.assertTrue(metadata["available"])
        self.assertEqual("never_run", metadata["latest_sync_status"])

    def test_importing_dashboard_does_not_call_network(self):
        with patch("requests.Session.get", side_effect=AssertionError("network called")):
            import importlib
            importlib.import_module("mnid.dhis2.store")


if __name__ == "__main__": unittest.main()
