"""Synchronization CLI safety tests."""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from mnid.dhis2.sync import main


MAPPING = {
    "schema_version": "1.0", "mapping_version": "test",
    "reporting_period": {"start_period": "202504", "end_period": "202605"},
    "indicators": [{"id": "a", "name": "A", "enabled": True, "value_type": "count", "calculation": {"operation": "direct", "operands": [{"dx": "A2345678901"}]}}],
}
UNITS = {"schema_version": "1.0", "organisation_units": [{"org_unit_id": "O2345678901", "enabled": True}]}


class SyncCliTests(unittest.TestCase):
    @patch("mnid.dhis2.sync.load_organisation_units", return_value=UNITS)
    @patch("mnid.dhis2.sync.load_indicator_mapping", return_value=MAPPING)
    def test_dry_run_does_not_require_credentials_or_call_ingestion(self, _mapping, _units):
        output = io.StringIO()
        with patch("mnid.dhis2.sync.run_ingestion") as ingestion, redirect_stdout(output):
            code = main(["--dry-run", "--start-period", "202504", "--end-period", "202605"])
        self.assertEqual(0, code); ingestion.assert_not_called()
        self.assertIn('"period_count": 14', output.getvalue())
        self.assertNotIn("password", output.getvalue().lower())

    def test_real_pilot_config_is_valid(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(["--validate-config"]))
        self.assertIn('"organisation_unit_count": 10406', output.getvalue())

    @patch.dict("os.environ", {"MNH_DHIS2_USERNAME": "u", "MNH_DHIS2_PASSWORD": "p"}, clear=False)
    def test_live_sync_refuses_mixed_levels(self):
        with patch("mnid.dhis2.sync.run_ingestion") as ingestion:
            self.assertEqual(2, main(["--start-period", "202504", "--end-period", "202504"]))
        ingestion.assert_not_called()


if __name__ == "__main__": unittest.main()
