"""
Proves FileTokenStore persistence survives across a genuinely fresh OS
process -- not just a fresh Python object or a fresh DigiKeyClient
instance within the same interpreter. This is the piece of the "restart"
guarantee this test suite CAN prove without an actual Yank PC reboot: two
real, independent `python` subprocesses sharing only a directory on disk.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"

WRITE_SCRIPT = """
import sys
sys.path.insert(0, {src!r})
from token_store import FileTokenStore

store = FileTokenStore({directory!r})
store.set("DIGIKEY_REFRESH_TOKEN", {value!r})
print("wrote-ok")
"""

READ_SCRIPT = """
import sys
sys.path.insert(0, {src!r})
from token_store import FileTokenStore

store = FileTokenStore({directory!r})
print(store.get("DIGIKEY_REFRESH_TOKEN") or "")
"""

ROTATE_TWICE_SCRIPT = """
import sys
sys.path.insert(0, {src!r})
from token_store import FileTokenStore

store = FileTokenStore({directory!r})
current = store.get("DIGIKEY_REFRESH_TOKEN")
store.set("DIGIKEY_REFRESH_TOKEN", current + "-rotated")
print("rotated-ok")
"""


def _run(script, **kwargs):
    code = script.format(src=str(SRC_FOLDER), **kwargs)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result


class FreshProcessPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_fresh_process_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_value_written_by_one_process_is_read_by_a_fresh_process(self):
        write_result = _run(WRITE_SCRIPT, directory=str(self.temp_dir), value="token-from-process-a")
        self.assertEqual(write_result.returncode, 0, write_result.stderr)
        self.assertIn("wrote-ok", write_result.stdout)

        read_result = _run(READ_SCRIPT, directory=str(self.temp_dir))
        self.assertEqual(read_result.returncode, 0, read_result.stderr)
        self.assertEqual(read_result.stdout.strip(), "token-from-process-a")

    def test_persistence_survives_three_independent_processes_in_sequence(self):
        """
        Simulates: process A writes (like an app instance authorizing
        DigiKey for the first time) -> process B reads and rotates (like
        the app restarting and doing a normal refresh) -> process C reads
        the ROTATED value (like the app restarting again afterward).
        Nothing here depends on any process's Python objects surviving --
        only the directory on disk.
        """
        write_result = _run(WRITE_SCRIPT, directory=str(self.temp_dir), value="T0")
        self.assertEqual(write_result.returncode, 0, write_result.stderr)

        rotate_result = _run(ROTATE_TWICE_SCRIPT, directory=str(self.temp_dir))
        self.assertEqual(rotate_result.returncode, 0, rotate_result.stderr)
        self.assertIn("rotated-ok", rotate_result.stdout)

        read_result = _run(READ_SCRIPT, directory=str(self.temp_dir))
        self.assertEqual(read_result.returncode, 0, read_result.stderr)
        self.assertEqual(read_result.stdout.strip(), "T0-rotated")

    def test_no_process_lives_long_enough_to_matter(self):
        """
        Each subprocess above exits completely before the next one
        starts (subprocess.run blocks until exit) -- this is not testing
        "the client object was garbage collected", it's testing "the OS
        process is gone and a brand new interpreter still sees the
        value", which is the actual restart-survival property a Windows
        service restart needs.
        """
        write_result = _run(WRITE_SCRIPT, directory=str(self.temp_dir), value="independent-of-process-lifetime")
        self.assertEqual(write_result.returncode, 0, write_result.stderr)

        for _ in range(3):
            read_result = _run(READ_SCRIPT, directory=str(self.temp_dir))
            self.assertEqual(read_result.stdout.strip(), "independent-of-process-lifetime")


if __name__ == "__main__":
    unittest.main()
