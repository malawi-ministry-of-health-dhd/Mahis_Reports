"""Unit tests for DHIS2 settings and monthly periods."""

import unittest
from datetime import date

from mnid.dhis2.exceptions import DHIS2ConfigurationError
from mnid.dhis2.periods import monthly_periods, period_end_date, period_start_date
from mnid.dhis2.settings import DHIS2Settings


class PeriodTests(unittest.TestCase):
    def test_required_range_has_fourteen_periods(self):
        periods = monthly_periods("202504", "202605")
        self.assertEqual(14, len(periods))
        self.assertEqual("202504", periods[0])
        self.assertEqual("202605", periods[-1])

    def test_same_month_and_dates(self):
        self.assertEqual(["202602"], monthly_periods("202602", "202602"))
        self.assertEqual(date(2024, 2, 1), period_start_date("202402"))
        self.assertEqual(date(2024, 2, 29), period_end_date("202402"))

    def test_invalid_and_reversed_ranges(self):
        for value in ("202500", "202513", "20251", "x02601"):
            with self.subTest(value=value), self.assertRaises(DHIS2ConfigurationError):
                monthly_periods(value, "202605")
        with self.assertRaises(DHIS2ConfigurationError):
            monthly_periods("202605", "202504")


class SettingsTests(unittest.TestCase):
    def test_defaults_do_not_require_credentials(self):
        settings = DHIS2Settings.from_env({})
        self.assertEqual("https://dhis2.health.gov.mw", settings.base_url)
        self.assertTrue(settings.verify_tls)
        self.assertEqual(14, len(monthly_periods(settings.start_period, settings.end_period)))

    def test_live_settings_require_credentials(self):
        with self.assertRaises(DHIS2ConfigurationError):
            DHIS2Settings.from_env({}, require_credentials=True)
        settings = DHIS2Settings.from_env(
            {"MNH_DHIS2_USERNAME": "service", "MNH_DHIS2_PASSWORD": "secret"},
            require_credentials=True,
        )
        self.assertEqual("service", settings.username)

    def test_invalid_values_fail(self):
        cases = [
            {"MNH_DHIS2_BASE_URL": "http://example.test"},
            {"MNH_DHIS2_VERIFY_TLS": "sometimes"},
            {"MNH_DHIS2_MAX_RETRIES": "-1"},
            {"MNH_DHIS2_DX_BATCH_SIZE": "0"},
            {"MNH_DHIS2_CONNECT_TIMEOUT_SECONDS": "fast"},
            {"MNH_DHIS2_START_PERIOD": "202513"},
        ]
        for env in cases:
            with self.subTest(env=env), self.assertRaises(DHIS2ConfigurationError):
                DHIS2Settings.from_env(env)


if __name__ == "__main__":
    unittest.main()
