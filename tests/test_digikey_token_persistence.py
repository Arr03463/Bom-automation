import contextlib
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from digikey_client import DigiKeyClient
from file_lock import FileLock, LockAcquisitionError
from token_store import (
    EnvFileTokenStore,
    FileTokenStore,
    HttpTokenStore,
    MemoryTokenStore,
    TokenStoreError,
    build_token_store,
    reset_shared_memory_token_store,
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

        reset_shared_memory_token_store()
        self.addCleanup(reset_shared_memory_token_store)

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

    def test_repeated_calls_share_the_same_memory_store_instance(self):
        os.environ["DIGIKEY_TOKEN_STORE"] = "memory"

        store_one = build_token_store()
        store_two = build_token_store()

        self.assertIs(store_one, store_two)

    def test_reset_creates_a_fresh_memory_store(self):
        os.environ["DIGIKEY_TOKEN_STORE"] = "memory"

        store_before = build_token_store()
        store_before.set("DIGIKEY_REFRESH_TOKEN", "value")

        reset_shared_memory_token_store()
        store_after = build_token_store()

        self.assertIsNot(store_before, store_after)
        self.assertIsNone(store_after.get("DIGIKEY_REFRESH_TOKEN"))


class DigiKeyClientSharedMemoryTokenStoreTests(unittest.TestCase):
    """
    Covers the specific regression: build_token_store() previously
    returned a brand-new MemoryTokenStore() on every call, so a token
    rotated by one DigiKeyClient() was invisible to the next DigiKeyClient()
    built moments later in the same process, even with no explicit
    token_store passed to either.
    """

    def setUp(self):
        self._saved_backend = os.environ.get("DIGIKEY_TOKEN_STORE")
        os.environ["DIGIKEY_TOKEN_STORE"] = "memory"
        self.addCleanup(self._restore_backend)

        reset_shared_memory_token_store()
        self.addCleanup(reset_shared_memory_token_store)

    def _restore_backend(self):
        if self._saved_backend is None:
            os.environ.pop("DIGIKEY_TOKEN_STORE", None)
        else:
            os.environ["DIGIKEY_TOKEN_STORE"] = self._saved_backend

    @patch("digikey_client.requests.post")
    def test_rotated_token_is_visible_to_a_later_client_in_the_same_process(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "access-token-a",
            "refresh_token": "rotated-by-client-a",
        }
        mock_post.return_value = mock_response

        # Client A: no explicit token_store, uses build_token_store()'s
        # default memory backend, and rotates its refresh token.
        client_a = DigiKeyClient()
        client_a.dry_run = False
        client_a.client_id = "test-client-id"
        client_a.client_secret = "test-client-secret"
        client_a.refresh_token = "original-token"
        client_a.user_access_token = ""

        client_a.get_user_access_token()
        self.assertEqual(client_a.refresh_token, "rotated-by-client-a")

        # Client B: constructed afterward, also with no explicit
        # token_store. It must see client A's rotated token, not fall back
        # to the stale static env value.
        client_b = DigiKeyClient()

        self.assertEqual(client_b.refresh_token, "rotated-by-client-a")


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


class HttpTokenStoreTests(unittest.TestCase):
    def test_missing_base_url_raises_token_store_error(self):
        store = HttpTokenStore(base_url="", api_key="key")
        with self.assertRaises(TokenStoreError):
            store.get("DIGIKEY_REFRESH_TOKEN")
        with self.assertRaises(TokenStoreError):
            store.set("DIGIKEY_REFRESH_TOKEN", "value")

    @patch("token_store.requests.get")
    def test_get_returns_none_for_404(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404)
        store = HttpTokenStore(base_url="https://kv.example.test/v1", api_key="key")

        self.assertIsNone(store.get("DIGIKEY_REFRESH_TOKEN"))

    @patch("token_store.requests.get")
    def test_get_returns_stored_value(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"value": "abc123"})
        store = HttpTokenStore(base_url="https://kv.example.test/v1", api_key="key")

        self.assertEqual(store.get("DIGIKEY_REFRESH_TOKEN"), "abc123")

    @patch("token_store.requests.get")
    def test_get_raises_on_network_failure(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("boom")
        store = HttpTokenStore(base_url="https://kv.example.test/v1", api_key="key")

        with self.assertRaises(TokenStoreError):
            store.get("DIGIKEY_REFRESH_TOKEN")

    @patch("token_store.requests.get")
    def test_get_raises_on_http_error_status(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        store = HttpTokenStore(base_url="https://kv.example.test/v1", api_key="key")

        with self.assertRaises(TokenStoreError):
            store.get("DIGIKEY_REFRESH_TOKEN")

    @patch("token_store.requests.put")
    def test_set_success(self, mock_put):
        mock_put.return_value = MagicMock(status_code=200)
        store = HttpTokenStore(base_url="https://kv.example.test/v1", api_key="key")

        self.assertTrue(store.set("DIGIKEY_REFRESH_TOKEN", "new-value"))
        called_url = mock_put.call_args[0][0]
        self.assertEqual(called_url, "https://kv.example.test/v1/DIGIKEY_REFRESH_TOKEN")

    @patch("token_store.requests.put")
    def test_set_raises_on_http_error_status(self, mock_put):
        mock_put.return_value = MagicMock(status_code=403)
        store = HttpTokenStore(base_url="https://kv.example.test/v1", api_key="key")

        with self.assertRaises(TokenStoreError):
            store.set("DIGIKEY_REFRESH_TOKEN", "new-value")

    def test_lock_is_a_noop_context_manager(self):
        store = HttpTokenStore(base_url="https://kv.example.test/v1", api_key="key")
        with store.lock():
            pass  # must not raise / must not require network access


class TokenStoreLockTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_token_lock_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_memory_token_store_lock_is_noop(self):
        store = MemoryTokenStore()
        with store.lock():
            pass

    def test_file_token_store_lock_returns_a_real_file_lock(self):
        store = FileTokenStore(self.temp_dir)
        with store.lock(timeout=1) as lock:
            self.assertIsInstance(lock, FileLock)
            self.assertTrue(lock.acquired)

    def test_env_file_token_store_lock_returns_a_real_file_lock(self):
        store = EnvFileTokenStore(self.temp_dir / ".env")
        with store.lock(timeout=1) as lock:
            self.assertIsInstance(lock, FileLock)
            self.assertTrue(lock.acquired)

    def test_file_token_store_lock_serializes_two_holders(self):
        store = FileTokenStore(self.temp_dir)
        first_holder_has_lock = threading.Event()
        second_holder_tried = threading.Event()
        second_holder_acquired_while_first_held = threading.Event()

        def hold_first():
            with store.lock(timeout=2):
                first_holder_has_lock.set()
                second_holder_tried.wait(timeout=2)

        def try_second():
            first_holder_has_lock.wait(timeout=2)
            lock = store.lock(timeout=0.3)
            try:
                with lock:
                    # Fail-closed (Codex F1): entering `with lock:` at all
                    # means acquisition succeeded, so reaching this line
                    # while the first holder is still active would itself
                    # be the bug.
                    second_holder_acquired_while_first_held.set()
            except LockAcquisitionError:
                pass
            second_holder_tried.set()

        thread_a = threading.Thread(target=hold_first)
        thread_b = threading.Thread(target=try_second)
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=3)
        thread_b.join(timeout=3)

        self.assertFalse(second_holder_acquired_while_first_held.is_set())


class DigiKeyClientTokenStoreErrorSurfacingTests(unittest.TestCase):
    def test_construction_falls_back_to_env_value_when_store_get_fails(self):
        store = MagicMock()
        store.get.side_effect = TokenStoreError("store unreachable")
        store.lock.return_value = contextlib.nullcontext()

        client = DigiKeyClient(token_store=store)

        self.assertEqual(client.token_store_error, "store unreachable")
        self.assertEqual(client.refresh_token, os.getenv("DIGIKEY_REFRESH_TOKEN", "").strip())

    @patch("digikey_client.requests.post")
    def test_rotation_updates_memory_even_when_persistence_fails(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "new-access", "refresh_token": "new-refresh"},
        )
        store = MagicMock()
        store.get.return_value = "old-refresh"
        store.set.side_effect = TokenStoreError("store unreachable")
        store.lock.return_value = contextlib.nullcontext()

        client = DigiKeyClient(token_store=store)
        client.dry_run = False
        client.client_id = "test-client-id"
        client.client_secret = "test-client-secret"
        client.user_access_token = ""

        token = client.get_user_access_token()

        self.assertEqual(token, "new-access")
        # In-memory continuity survives even though the durable write
        # failed -- losing only the persisted copy (recoverable on
        # restart via re-auth) is safer than also losing in-process state
        # DigiKey has already invalidated the old value for.
        self.assertEqual(client.refresh_token, "new-refresh")
        self.assertEqual(client.token_store_error, "store unreachable")


class DigiKeyClientConcurrentRotationTests(unittest.TestCase):
    """
    Regression coverage for the durable-token concurrency requirement:
    two DigiKeyClient instances sharing the same FileTokenStore directory
    (simulating two processes/threads racing a near-simultaneous refresh)
    must not both submit the same now-stale refresh token to DigiKey. The
    lock + re-read-under-lock in get_user_access_token()/
    _current_refresh_token() must serialize them so the second caller
    picks up the first caller's already-rotated token before attempting
    its own refresh.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_digikey_rotation_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def _make_client(self, store, initial_refresh_token):
        client = DigiKeyClient(token_store=store)
        client.dry_run = False
        client.client_id = "test-client-id"
        client.client_secret = "test-client-secret"
        client.refresh_token = initial_refresh_token
        client.user_access_token = ""
        return client

    def test_two_concurrent_clients_never_submit_an_already_rotated_token(self):
        store = FileTokenStore(self.temp_dir)
        store.set("DIGIKEY_REFRESH_TOKEN", "T0")

        server_lock = threading.Lock()
        state = {"current": "T0", "rotations": 0, "rejected": []}

        def fake_post(url, data=None, timeout=None):
            with server_lock:
                submitted = (data or {}).get("refresh_token")
                response = MagicMock()
                if submitted != state["current"]:
                    state["rejected"].append(submitted)
                    response.status_code = 400
                    response.raise_for_status.side_effect = requests.HTTPError("invalid_grant")
                    response.json.return_value = {"error": "invalid_grant"}
                    response.text = "invalid_grant"
                    return response

                state["rotations"] += 1
                new_token = f"T{state['rotations']}"
                state["current"] = new_token
                response.status_code = 200
                response.raise_for_status.return_value = None
                response.json.return_value = {
                    "access_token": f"access-{state['rotations']}",
                    "refresh_token": new_token,
                }
                return response

        client_a = self._make_client(store, "T0")
        client_b = self._make_client(store, "T0")
        results = {}
        errors = {}

        def run(name, client):
            try:
                results[name] = client.get_user_access_token()
            except Exception as exc:  # pragma: no cover - failure path asserted below
                errors[name] = exc

        with patch("digikey_client.requests.post", side_effect=fake_post):
            thread_a = threading.Thread(target=run, args=("a", client_a))
            thread_b = threading.Thread(target=run, args=("b", client_b))
            thread_a.start()
            thread_b.start()
            thread_a.join(timeout=5)
            thread_b.join(timeout=5)

        self.assertEqual(errors, {})
        self.assertEqual(set(results.keys()), {"a", "b"})
        self.assertEqual(state["rejected"], [])
        self.assertEqual(state["rotations"], 2)
        self.assertEqual(store.get("DIGIKEY_REFRESH_TOKEN"), state["current"])

    def test_lock_timeout_makes_zero_digikey_requests(self):
        """
        Codex F1: a caller that cannot acquire the token-store lock must
        make ZERO DigiKey refresh-token HTTP requests -- not a request
        with a stale token, not a "best effort" request. Holds the lock
        externally (simulating another process/thread's in-progress
        refresh) and asserts requests.post is never called.
        """
        store = FileTokenStore(self.temp_dir)
        store.set("DIGIKEY_REFRESH_TOKEN", "T0")
        client = self._make_client(store, "T0")

        blocking_lock = FileLock(self.temp_dir / "_rotation", timeout=5)
        self.assertTrue(blocking_lock.acquire())
        try:
            # Short per-call timeout so the test doesn't wait for the
            # store's own (120s) default. Builds a fresh FileLock rather
            # than calling store.lock() again, to avoid patching over
            # itself.
            with patch.object(
                store,
                "lock",
                lambda timeout=None: FileLock(self.temp_dir / "_rotation", timeout=0.2),
            ):
                with patch("digikey_client.requests.post") as mock_post:
                    with self.assertRaises(RuntimeError) as ctx:
                        client.get_user_access_token()

            mock_post.assert_not_called()
            self.assertIn("busy", str(ctx.exception).lower())
        finally:
            blocking_lock.release()


class DigiKeyTokenPersistenceFailureDegradesResultTests(unittest.TestCase):
    """
    Codex F2: a successful DigiKey refresh whose rotated-token PERSISTENCE
    fails must not be indistinguishable from a fully healthy rotation.
    DigiKeyClient itself already records token_store_error (see
    DigiKeyClientTokenStoreErrorSurfacingTests); this covers that it
    survives into create_digikey_mylist_from_bom()'s returned dict, which
    is what workflow_runner.py's artifact-status logic reads (see
    tests/test_purchasing_state.py for the workflow_runner-level
    assertion that this degrades the reported artifact status).
    """

    def test_create_mylist_result_carries_token_store_error(self):
        import digikey_mylists_client as dm

        fake_auth_client = MagicMock()
        fake_auth_client.get_user_access_token.return_value = "access-token"
        fake_auth_client.token_store_error = "store unreachable"

        with patch.object(dm.DigiKeyMyListsClient, "__init__", lambda self: None):
            client = dm.DigiKeyMyListsClient()
            client.auth_client = fake_auth_client
            client.dry_run = True
            client.enabled = True
            client.client_id = "id"
            client.account_id = ""

        with patch("digikey_mylists_client.DigiKeyMyListsClient", return_value=client):
            with patch(
                "digikey_mylists_client.build_digikey_mylists_parts",
                return_value=[{"RequestedPartNumber": "X"}],
            ):
                result = dm.create_digikey_mylist_from_bom(
                    clean_bom=object(), list_name="Test List"
                )

        self.assertTrue(result["created"])
        self.assertEqual(result["token_store_error"], "store unreachable")

    def test_create_mylist_result_has_no_token_store_error_when_healthy(self):
        import digikey_mylists_client as dm

        fake_auth_client = MagicMock()
        fake_auth_client.get_user_access_token.return_value = "access-token"
        fake_auth_client.token_store_error = None

        with patch.object(dm.DigiKeyMyListsClient, "__init__", lambda self: None):
            client = dm.DigiKeyMyListsClient()
            client.auth_client = fake_auth_client
            client.dry_run = True
            client.enabled = True
            client.client_id = "id"
            client.account_id = ""

        with patch("digikey_mylists_client.DigiKeyMyListsClient", return_value=client):
            with patch(
                "digikey_mylists_client.build_digikey_mylists_parts",
                return_value=[{"RequestedPartNumber": "X"}],
            ):
                result = dm.create_digikey_mylist_from_bom(
                    clean_bom=object(), list_name="Test List"
                )

        self.assertTrue(result["created"])
        self.assertIsNone(result["token_store_error"])


if __name__ == "__main__":
    unittest.main()
