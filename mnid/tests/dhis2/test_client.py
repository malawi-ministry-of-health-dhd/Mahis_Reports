"""Mocked tests for secure request behaviour and Analytics parsing."""

import unittest
from unittest.mock import Mock

import requests

from mnid.dhis2.client import DHIS2Client, parse_analytics_response
from mnid.dhis2.exceptions import DHIS2AuthenticationError, DHIS2RequestError, DHIS2ResponseError, DHIS2TimeoutError
from mnid.dhis2.settings import DHIS2Settings


def settings(retries=0):
    return DHIS2Settings.from_env({
        "MNH_DHIS2_USERNAME": "service", "MNH_DHIS2_PASSWORD": "not-logged",
        "MNH_DHIS2_MAX_RETRIES": str(retries),
    }, require_credentials=True)


def response(status=200, payload=None, content_type="application/json"):
    result = Mock()
    result.status_code = status
    result.headers = {"Content-Type": content_type}
    result.json.return_value = payload if payload is not None else {"headers": [], "rows": []}
    return result


class ClientTests(unittest.TestCase):
    def test_success_uses_tls_timeouts_and_dimensions(self):
        session = Mock()
        session.headers = {}
        session.get.return_value = response(payload={"headers": [], "rows": []})
        client = DHIS2Client(settings(), session=session)
        result = client.analytics(["iBBnHx1Uf50"], ["202504"], ["Abc12345678"], sync_run_id="run", request_id="r1")
        self.assertEqual([], result["rows"])
        kwargs = session.get.call_args.kwargs
        self.assertTrue(kwargs["verify"])
        self.assertEqual((10, 60), kwargs["timeout"])
        self.assertNotIn("not-logged", str(kwargs))

    def test_permanent_errors_are_not_retried(self):
        for status, error in ((400, DHIS2RequestError), (401, DHIS2AuthenticationError), (403, Exception)):
            session = Mock(); session.headers = {}; session.get.return_value = response(status=status)
            with self.subTest(status=status), self.assertRaises(error):
                DHIS2Client(settings(3), session=session).analytics(["iBBnHx1Uf50"], ["202504"], ["Abc12345678"], sync_run_id="run", request_id="r1")
            self.assertEqual(1, session.get.call_count)

    def test_transient_failure_then_success(self):
        session = Mock(); session.headers = {}
        session.get.side_effect = [response(status=500), response(payload={"headers": [], "rows": []})]
        sleeps = []
        result = DHIS2Client(settings(1), session=session, sleep=sleeps.append).analytics(["iBBnHx1Uf50"], ["202504"], ["Abc12345678"], sync_run_id="run", request_id="r1")
        self.assertEqual([], result["rows"])
        self.assertEqual([1.0], sleeps)

    def test_timeout_is_typed(self):
        session = Mock(); session.headers = {}; session.get.side_effect = requests.Timeout("secret-free")
        with self.assertRaises(DHIS2TimeoutError):
            DHIS2Client(settings(), session=session).analytics(["iBBnHx1Uf50"], ["202504"], ["Abc12345678"], sync_run_id="run", request_id="r1")

    def test_invalid_content_type_and_shape(self):
        session = Mock(); session.headers = {}; session.get.return_value = response(content_type="text/html")
        with self.assertRaises(DHIS2ResponseError):
            DHIS2Client(settings(), session=session).analytics(["iBBnHx1Uf50"], ["202504"], ["Abc12345678"], sync_run_id="run", request_id="r1")


class ParserTests(unittest.TestCase):
    def test_dynamic_headers_explicit_zero_and_rejections(self):
        payload = {
            "headers": [{"name": "value"}, {"name": "ou"}, {"name": "dx"}, {"name": "pe"}, {"name": "extra"}],
            "rows": [
                ["0", "Abc12345678", "iBBnHx1Uf50", "202504", "kept"],
                ["bad", "Abc12345678", "EeywK6AHQdK", "202504", "x"],
                ["1", "Abc12345678", "iBBnHx1Uf50", "202504", "duplicate"],
            ],
        }
        values, rejected = parse_analytics_response(payload)
        self.assertEqual(1, len(values)); self.assertEqual(0, values[0].value)
        self.assertEqual(2, len(rejected))

    def test_missing_headers_fail(self):
        with self.assertRaises(DHIS2ResponseError):
            parse_analytics_response({"headers": [{"name": "dx"}], "rows": []})


if __name__ == "__main__":
    unittest.main()
