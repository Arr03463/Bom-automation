import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

import deployment_preflight as preflight
from token_store import reset_shared_memory_token_store

ENV_KEYS = (
    "DIGIKEY_TOKEN_STORE",
    "DIGIKEY_TOKEN_STORE_PATH",
    "DIGIKEY_TOKEN_STORE_URL",
    "DIGIKEY_TOKEN_STORE_ENV_PATH",
    "DIGIKEY_MYLISTS_ENABLED",
    "DIGIKEY_CLIENT_ID",
    "DIGIKEY_CLIENT_SECRET",
    "MOUSER_CART_ENABLED",
    "MOUSER_CART_API_KEY",
    "PARTSBOX_API_KEY",
    "AUTOBOM_RUNS_ROOT",
    "AUTOBOM_CACHE_ROOT",
    "AUTOBOM_LOGS_DIR",
    "STREAMLIT_SERVER_ENABLE_CORS",
    "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION",
)


class PreflightTestCase(unittest.TestCase):
    def setUp(self):
        self._saved_env = {key: os.environ.pop(key, None) for key in ENV_KEYS}
        # Deterministic memory fallback regardless of this machine's real .env.
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


class CheckWritableDirectoryTests(PreflightTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_preflight_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_writable_directory_passes(self):
        result = preflight.check_writable_directory("Test dir", self.temp_dir / "sub")
        self.assertEqual(result["status"], preflight.PASS)

    def test_leaves_no_probe_file_behind(self):
        preflight.check_writable_directory("Test dir", self.temp_dir)
        leftovers = list(self.temp_dir.glob(".preflight-*.tmp"))
        self.assertEqual(leftovers, [])

    def test_unwritable_path_fails(self):
        # A file where a directory is expected can never be mkdir'd into.
        blocker = self.temp_dir / "blocker"
        blocker.write_text("x", encoding="utf-8")
        result = preflight.check_writable_directory("Test dir", blocker / "nested")
        self.assertEqual(result["status"], preflight.FAIL)


class CheckFileTokenStoreTests(PreflightTestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_preflight_token_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_all_checks_pass_for_a_directory_outside_the_checkout(self):
        checks = preflight.check_file_token_store(self.temp_dir)
        names = {c["name"]: c["status"] for c in checks}

        self.assertEqual(names["Token directory exists/creatable"], preflight.PASS)
        self.assertEqual(names["Token store read/write/atomic replace"], preflight.PASS)
        self.assertEqual(names["Token store lock acquire/release"], preflight.PASS)
        self.assertEqual(names["Token directory location"], preflight.PASS)

    def test_leaves_no_probe_key_file_behind(self):
        preflight.check_file_token_store(self.temp_dir)
        leftovers = [p for p in self.temp_dir.iterdir() if "_preflight_probe_" in p.name]
        self.assertEqual(leftovers, [])

    def test_directory_inside_checkout_warns(self):
        inside = PROJECT_ROOT / ".cache" / "preflight_inside_checkout_test"
        self.addCleanup(shutil.rmtree, inside, ignore_errors=True)

        checks = preflight.check_file_token_store(inside)
        names = {c["name"]: c["status"] for c in checks}

        self.assertEqual(names["Token directory location"], preflight.WARN)


class CheckDigikeyTokenStoreResolutionTests(PreflightTestCase):
    def test_file_backend_without_path_fails(self):
        os.environ["DIGIKEY_TOKEN_STORE"] = "file"
        result = preflight.check_digikey_token_store_resolution()
        self.assertEqual(result["status"], preflight.FAIL)

    def test_http_backend_without_url_fails(self):
        os.environ["DIGIKEY_TOKEN_STORE"] = "http"
        result = preflight.check_digikey_token_store_resolution()
        self.assertEqual(result["status"], preflight.FAIL)

    def test_memory_with_mylists_enabled_warns(self):
        os.environ["DIGIKEY_TOKEN_STORE"] = "memory"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"
        result = preflight.check_digikey_token_store_resolution()
        self.assertEqual(result["status"], preflight.WARN)

    def test_memory_with_mylists_disabled_passes(self):
        os.environ["DIGIKEY_TOKEN_STORE"] = "memory"
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "false"
        result = preflight.check_digikey_token_store_resolution()
        self.assertEqual(result["status"], preflight.PASS)

    def test_file_backend_with_path_and_mylists_enabled_passes(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="autobom_preflight_resolution_test_"))
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        os.environ["DIGIKEY_TOKEN_STORE"] = "file"
        os.environ["DIGIKEY_TOKEN_STORE_PATH"] = str(temp_dir)
        os.environ["DIGIKEY_MYLISTS_ENABLED"] = "true"

        result = preflight.check_digikey_token_store_resolution()

        self.assertEqual(result["status"], preflight.PASS)


class RunPreflightTests(PreflightTestCase):
    def test_returns_overall_and_checks(self):
        result = preflight.run_preflight()

        self.assertIn(result["overall"], (preflight.PASS, preflight.WARN, preflight.FAIL))
        self.assertTrue(result["checks"])
        for entry in result["checks"]:
            self.assertIn(entry["status"], (preflight.PASS, preflight.WARN, preflight.FAIL))

    def test_overall_is_worst_of_individual_checks(self):
        os.environ["DIGIKEY_TOKEN_STORE"] = "file"  # forces a FAIL (no path set)

        result = preflight.run_preflight()

        self.assertEqual(result["overall"], preflight.FAIL)

    def test_never_raises_creates_no_vendor_side_effect(self):
        """
        Preflight must be safe to run repeatedly against a real
        deployment: no exception, and by construction (it never imports
        mouser_cart_client.create_mouser_cart_from_bom or
        digikey_mylists_client.create_digikey_mylist_from_bom) no vendor
        cart/MyList call.
        """
        import inspect

        source = inspect.getsource(preflight)
        self.assertNotIn("create_mouser_cart_from_bom", source)
        self.assertNotIn("create_digikey_mylist_from_bom", source)

        preflight.run_preflight()  # must not raise

    def test_format_report_includes_overall_and_every_check(self):
        result = preflight.run_preflight()
        report = preflight.format_report(result)

        self.assertIn(result["overall"], report)
        for entry in result["checks"]:
            self.assertIn(entry["name"], report)


if __name__ == "__main__":
    unittest.main()
