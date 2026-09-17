import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from digikey_client import DigiKeyClient
from token_store import (
    EnvFileTokenStore,
    FileTokenStore,
    MemoryTokenStore,
    build_token_store,
)


class MemoryTokenStoreTests(unittest.TestCase):
    def test_set_then_get_round_trip(self):
        store = MemoryTokenStore()
        store.set("KEY", "value")
        self.assertEqual(store.get("KEY"), "value")

    def test_get_missing_returns_none(self):
        store = MemoryTokenStore()
        self.assertIsNone(store.get("missing"))


class EnvFileTokenStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_token_store_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.env_path = self.temp_dir / ".env"

    def test_get_returns_none_when_file_missing(self):
        store = EnvFileTokenStore(self.env_path)
        self.assertIsNone(store.get("DIGIKEY_REFRESH_TOKEN"))

    def test_set_updates_existing_key_in_place(self):
        self.env_path.write_text(
            "DIGIKEY_REFRESH_TOKEN=old-token\nOTHER_KEY=value\n", encoding="utf-8"
        )
        store = EnvFileTokenStore(self.env_path)

        store.set("DIGIKEY_REFRESH_TOKEN", "new-token")

        self.assertEqual(store.get("DIGIKEY_REFRESH_TOKEN"), "new-token")
        self.assertIn("OTHER_KEY=value", self.env_path.read_text(encoding="utf-8"))

    def test_set_appends_key_missing_from_existing_file(self):
        self.env_path.write_text("OTHER_KEY=value\n", encoding="utf-8")
        store = EnvFileTokenStore(self.env_path)

        store.set("DIGIKEY_REFRESH_TOKEN", "brand-new-token")

        self.assertEqual(store.get("DIGIKEY_REFRESH_TOKEN"), "brand-new-token")

    def test_set_creates_file_when_missing(self):
        store = EnvFileTokenStore(self.env_path)
        store.set("DIGIKEY_REFRESH_TOKEN", "created-token")

        self.assertTrue(self.env_path.exists())
        self.assertEqual(store.get("DIGIKEY_REFRESH_TOKEN"), "created-token")


class FileTokenStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_file_token_store_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_set_then_get_round_trip(self):
        store = FileTokenStore(self.temp_dir)
        store.set("DIGIKEY_REFRESH_TOKEN", "abc123")

        self.assertEqual(store.get("DIGIKEY_REFRESH_TOKEN"), "abc123")

    def test_get_returns_none_when_missing(self):
        store = FileTokenStore(self.temp_dir)
        self.assertIsNone(store.get("DIGIKEY_REFRESH_TOKEN"))

    def test_no_leftover_tmp_files_after_write(self):
        store = FileTokenStore(self.temp_dir)
        store.set("DIGIKEY_REFRESH_TOKEN", "abc123")

        leftovers = list(self.temp_dir.glob("*.tmp"))
        self.assertEqual(leftovers, [])


class BuildTokenStoreSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_build_store_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

        self._saved_env = {}
        for key in ("DIGIKEY_TOKEN_STORE", "DIGIKEY_TOKEN_STORE_PATH", "DIGIKEY_TOKEN_STORE_ENV_PATH"):
            self._saved_env[key] = os.environ.pop(key, None)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_explicit_memory_backend(self):
        os.environ["DIGIKEY_TOKEN_STORE"] = "memory"
        self.assertIsInstance(build_token_store(), MemoryTokenStore)

    def test_explicit_file_backend_with_path(self):
        os.environ["DIGIKEY_TOKEN_STORE"] = "file"
        os.environ["DIGIKEY_TOKEN_STORE_PATH"] = str(self.temp_dir)
        self.assertIsInstance(build_token_store(), FileTokenStore)

    def test_file_backend_without_path_falls_back_to_memory(self):
        # Documents the cloud limitation explicitly: asking for a
        # persistent file-backed store without a configured directory must
        # not silently write into the repository -- it degrades to
        # in-process only rather than guessing a location.
        os.environ["DIGIKEY_TOKEN_STORE"] = "file"
        self.assertIsInstance(build_token_store(), MemoryTokenStore)

    def test_env_file_backend_auto_selected_when_target_path_exists(self):
        env_path = self.temp_dir / ".env"
        env_path.write_text("DIGIKEY_REFRESH_TOKEN=abc\n", encoding="utf-8")
        os.environ["DIGIKEY_TOKEN_STORE_ENV_PATH"] = str(env_path)

        store = build_token_store()

        self.assertIsInstance(store, EnvFileTokenStore)
        self.assertEqual(store.env_path, env_path)

    def test_memory_backend_auto_selected_when_target_env_path_missing(self):
        os.environ["DIGIKEY_TOKEN_STORE_ENV_PATH"] = str(self.temp_dir / "does-not-exist.env")
        self.assertIsInstance(build_token_store(), MemoryTokenStore)


class DigiKeyClientRefreshTokenTests(unittest.TestCase):
    def test_stored_refresh_token_takes_precedence_over_env_value(self):
        store = MemoryTokenStore()
        store.set("DIGIKEY_REFRESH_TOKEN", "stored-rotated-token")

        client = DigiKeyClient(token_store=store)

        self.assertEqual(client.refresh_token, "stored-rotated-token")

    def test_falls_back_to_env_value_when_store_has_nothing(self):
        store = MemoryTokenStore()
        client = DigiKeyClient(token_store=store)

        self.assertEqual(client.refresh_token, os.getenv("DIGIKEY_REFRESH_TOKEN", "").strip())

    def test_dry_run_returns_placeholder_without_touching_store(self):
        store = MagicMock()
        store.get.return_value = None
        client = DigiKeyClient(token_store=store)
        client.dry_run = True

        token = client.get_user_access_token()

        self.assertEqual(token, "dry-run-token")
        store.set.assert_not_called()

    def test_missing_refresh_token_raises_value_error(self):
        client = DigiKeyClient(token_store=MemoryTokenStore())
        client.dry_run = False
        client.refresh_token = ""
        client.user_access_token = ""

        with self.assertRaises(ValueError):
            client.get_user_access_token()

    @patch("digikey_client.requests.post")
    def test_rotated_refresh_token_is_persisted_and_not_logged(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
        }
        mock_post.return_value = mock_response

        store = MemoryTokenStore()
        client = DigiKeyClient(token_store=store)
        client.dry_run = False
        client.client_id = "test-client-id"
        client.client_secret = "test-client-secret"
        client.refresh_token = "old-refresh-token"
        client.user_access_token = ""

        with patch("builtins.print") as mock_print:
            token = client.get_user_access_token()

        self.assertEqual(token, "new-access-token")
        self.assertEqual(client.refresh_token, "new-refresh-token")
        self.assertEqual(store.get("DIGIKEY_REFRESH_TOKEN"), "new-refresh-token")
        mock_print.assert_not_called()

    @patch("digikey_client.requests.post")
    def test_unrotated_refresh_token_does_not_write_to_store(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "same-refresh-token",
        }
        mock_post.return_value = mock_response

        store = MemoryTokenStore()
        client = DigiKeyClient(token_store=store)
        client.dry_run = False
        client.client_id = "test-client-id"
        client.client_secret = "test-client-secret"
        client.refresh_token = "same-refresh-token"
        client.user_access_token = ""

        client.get_user_access_token()

        self.assertIsNone(store.get("DIGIKEY_REFRESH_TOKEN"))


if __name__ == "__main__":
    unittest.main()
