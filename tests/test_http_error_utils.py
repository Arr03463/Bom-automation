import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from http_error_utils import describe_error_response, raise_for_status


def fake_response(status_code, json_value=None, json_raises=False, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    if json_raises:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = json_value
    return response


class DescribeErrorResponseTests(unittest.TestCase):
    def test_extracts_known_error_field(self):
        response = fake_response(
            400, json_value={"error": "invalid_grant", "error_description": "Refresh token expired"}
        )

        result = describe_error_response(response)

        self.assertIn("HTTP 400", result)
        self.assertIn("invalid_grant", result)

    def test_extracts_vendor_style_message_and_request_id(self):
        response = fake_response(
            500,
            json_value={"ErrorMessage": "Something went wrong", "RequestId": "req-123"},
        )

        result = describe_error_response(response)

        self.assertIn("Something went wrong", result)
        self.assertIn("req-123", result)

    def test_non_json_body_falls_back_to_generic_message_not_raw_text(self):
        secret_looking_text = "apiKey=super-secret-value-should-not-appear"
        response = fake_response(502, json_raises=True, text=secret_looking_text)

        result = describe_error_response(response)

        self.assertNotIn(secret_looking_text, result)
        self.assertNotIn("super-secret-value", result)
        self.assertIn("HTTP 502", result)

    def test_json_body_with_no_known_fields_does_not_leak_other_fields(self):
        response = fake_response(
            400,
            json_value={"unexpected_field": "apiKey=super-secret-value", "another": "client_secret=abc"},
        )

        result = describe_error_response(response)

        self.assertNotIn("super-secret-value", result)
        self.assertNotIn("client_secret=abc", result)
        self.assertIn("no structured error details in response", result)

    def test_long_message_is_truncated(self):
        long_message = "x" * 1000
        response = fake_response(400, json_value={"message": long_message})

        result = describe_error_response(response, max_length=50)

        self.assertLessEqual(len(result), 50 + len("HTTP 400: "))
        self.assertTrue(result.endswith("..."))


class RaiseForStatusTests(unittest.TestCase):
    def test_success_response_does_not_raise(self):
        response = fake_response(200, json_value={})
        response.raise_for_status.return_value = None

        raise_for_status(response, "some request")  # must not raise

    def test_error_response_raises_runtime_error_with_context(self):
        response = fake_response(400, json_value={"error": "invalid_grant"})
        response.raise_for_status.side_effect = requests.HTTPError("bad request")

        with self.assertRaises(RuntimeError) as ctx:
            raise_for_status(response, "DigiKey token request failed")

        self.assertIn("DigiKey token request failed", str(ctx.exception))
        self.assertIn("invalid_grant", str(ctx.exception))

    def test_raw_body_never_appears_in_the_raised_message(self):
        secret_looking_text = "apiKey=super-secret-value-should-not-appear"
        response = fake_response(502, json_raises=True, text=secret_looking_text)
        response.raise_for_status.side_effect = requests.HTTPError("bad gateway")

        with self.assertRaises(RuntimeError) as ctx:
            raise_for_status(response, "Mouser cart request failed")

        self.assertNotIn(secret_looking_text, str(ctx.exception))
        self.assertNotIn("super-secret-value", str(ctx.exception))


class SharedRaiseForStatusReuseTests(unittest.TestCase):
    """
    digikey_client.py, digikey_mylists_client.py, and mouser_client.py
    previously each defined their own near-identical _raise_for_status(),
    two of which fell back to the raw response body/reason text instead
    of describe_error_response()'s allow-list. Guard against that
    regressing by asserting all three now import the shared
    implementation rather than defining their own.
    """

    def test_vendor_clients_import_the_shared_helper(self):
        import digikey_client
        import digikey_mylists_client
        import mouser_client
        import http_error_utils

        self.assertIs(digikey_client._raise_for_status, http_error_utils.raise_for_status)
        self.assertIs(digikey_mylists_client._raise_for_status, http_error_utils.raise_for_status)
        self.assertIs(mouser_client._raise_for_status, http_error_utils.raise_for_status)


if __name__ == "__main__":
    unittest.main()
