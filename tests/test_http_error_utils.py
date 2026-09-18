import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from http_error_utils import describe_error_response


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


if __name__ == "__main__":
    unittest.main()
