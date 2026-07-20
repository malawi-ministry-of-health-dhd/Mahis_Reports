"""Smoke tests for the MNH HMIS sample dashboard."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from mnid.dashboards import load_dashboard_module


class HmisTestDashboardTests(unittest.TestCase):
    def test_dashboard_loads_five_local_indicators(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.parquet"
            pd.DataFrame([{"indicator_id": f"i{i}", "indicator_name": f"Indicator {i}", "period": "202504", "period_start": "2025-04-01", "org_unit_id": "ou1", "org_unit_name": "Facility", "district": "District", "facility_code": "F1", "value": i} for i in range(5)]).to_parquet(path, index=False)
            module = load_dashboard_module("MNH-HMIS-Test")
            result = module.render_mnh_hmis_test_dashboard(start_date="2025-04-01", end_date="2025-04-30", scope_meta={"selected_districts": ["District"]}, data_path=path)
            rendered = str(result)
            self.assertIn("MNH HMIS test", rendered)
            for i in range(5): self.assertIn(f"Indicator {i}", rendered)


if __name__ == "__main__": unittest.main()
