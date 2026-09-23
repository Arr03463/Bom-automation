import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from config_validation import (
    collect_startup_warnings,
    digikey_mylists_config_status,
    mouser_cart_config_status,
    partsbox_config_status,
)
from token_store import reset_shared_memory_token_store

ENV_KEYS = (
    "DIGIKEY_MYLISTS_ENABLED",
    "DIGIKEY_CLIENT_ID",
    "DIGIKEY_CLIENT_SECRET",
    "DIGIKEY_TOKEN_STORE",
    "DIGIKEY_TOKEN_STORE_PATH",
    "DIGIKEY_TOKEN_STORE_ENV_PATH",
    "MOUSER_CART_ENABLED",
    "MOUSER_CART_API_KEY",
    "PARTSBOX_API_KEY",
)


class ConfigValidationTestCase(unittest.TestCase):
    def setUp(self):
        self._saved_env = {key: os.environ.pop(key, None) for key in ENV_KEYS}
        # Point the env_file backend at a location that doesn't exist so
        # build_token_store() falls back to memory deterministically,
        # regardless of this machine's real .env.
        os.environ["DIGIKEY_TOKEN_STORE_ENV_PATH"] = str(PROJECT_ROOT / "does-not-exist.env")
        reset_shared_memory_token_store()
        self.addCleanup(reset_shared_memory_token_store)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class DigiKeyMyListsConfigStatusTests(ConfigValidationTestCase):
    def test_disabled_produces_no_warning(self):
        status = digikey_mylists_config_status()
        self.assertFalse(status["enabled"])
        self.assertIsNone(status["warning"])

    def test_enabled_with_memory_backend_warns_not_durable(self):
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"
        os.environ["DIGIKEY_CLIENT_ID"] = "id"
        os.environ["DIGIKEY_CLIENT_SECRET"] = "secret"
        os.environ["DIGIKEY_TOKEN_STORE"] = "memory"

        status = digikey_mylists_config_status()

        self.assertTrue(status["enabled"])
        self.assertFalse(status["durable"])
        self.assertIn("in-process only", status["warning"])

    def test_enabled_with_file_backend_is_durable_no_warning(self):
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"
        os.environ["DIGIKEY_CLIENT_ID"] = "id"
        os.environ["DIGIKEY_CLIENT_SECRET"] = "secret"
        os.environ["DIGIKEY_TOKEN_STORE"] = "file"
        os.environ["DIGIKEY_TOKEN_STORE_PATH"] = str(PROJECT_ROOT / ".cache" / "token_store_test")

        status = digikey_mylists_config_status()

        self.assertTrue(status["durable"])
        self.assertIsNone(status["warning"])

    def test_enabled_without_credentials_warns_missing_credentials(self):
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"

        status = digikey_mylists_config_status()

        self.assertIn("credentials are missing", status["warning"])
        self.assertIn("DIGIKEY_CLIENT_ID", status["warning"])

    def test_missing_credentials_takes_priority_over_durability_warning(self):
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"
        os.environ["DIGIKEY_TOKEN_STORE"] = "memory"
        # No client id/secret set.

        status = digikey_mylists_config_status()

        self.assertIn("credentials are missing", status["warning"])


class MouserCartConfigStatusTests(ConfigValidationTestCase):
    def test_disabled_produces_no_warning(self):
        status = mouser_cart_config_status()
        self.assertFalse(status["enabled"])
        self.assertIsNone(status["warning"])

    def test_enabled_without_api_key_warns(self):
        os.environ["MOUSER_CART_ENABLED"] = "true"

        status = mouser_cart_config_status()

        self.assertIn("MOUSER_CART_API_KEY", status["warning"])

    def test_enabled_with_api_key_has_no_warning(self):
        os.environ["MOUSER_CART_ENABLED"] = "true"
        os.environ["MOUSER_CART_API_KEY"] = "key"

        status = mouser_cart_config_status()

        self.assertIsNone(status["warning"])


class PartsBoxConfigStatusTests(ConfigValidationTestCase):
    def test_missing_api_key_warns(self):
        status = partsbox_config_status()
        self.assertFalse(status["configured"])
        self.assertIsNotNone(status["warning"])

    def test_present_api_key_has_no_warning(self):
        os.environ["PARTSBOX_API_KEY"] = "key"

        status = partsbox_config_status()

        self.assertTrue(status["configured"])
        self.assertIsNone(status["warning"])


class CollectStartupWarningsTests(ConfigValidationTestCase):
    def test_clean_config_produces_no_warnings(self):
        os.environ["PARTSBOX_API_KEY"] = "key"
        # DigiKey and Mouser cart automation both left disabled.

        self.assertEqual(collect_startup_warnings(), [])

    def test_multiple_problems_all_surface(self):
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"
        os.environ["MOUSER_CART_ENABLED"] = "true"

        warnings = collect_startup_warnings()

        self.assertEqual(len(warnings), 3)  # DigiKey creds, Mouser creds, PartsBox creds


if __name__ == "__main__":
    unittest.main()
