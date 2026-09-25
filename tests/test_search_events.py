"""
Tests for search_events.search_event_input() -- the minimal CCv2 Enter-
event adapter.

IMPORTANT LIMITATION: streamlit.testing.v1.AppTest does not execute a
custom component's frontend JS (there is no real browser in this test
context), so these tests can only verify the Python-side contract: the
component mounts without exceptions, exposes the documented
`.value`/`.submitted` result shape, and defaults `.value` to the seeded
value (not None) before any browser has run the JS. The actual debounce
timing and Enter-vs-typing distinction live entirely in the frontend JS
(src/search_events.py's _JS string) and must be verified manually in a
real browser -- this is disclosed in the implementation report.
"""

import sys
import unittest
from pathlib import Path
from textwrap import dedent

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from streamlit.testing.v1 import AppTest


def _fresh_apptest(harness_path):
    """
    Each AppTest instance below runs in its own isolated component-registry
    context, but Python only executes a module's top-level code (including
    search_events.py's `st.components.v2.component(...)` registration
    call) the FIRST time it's imported in this process. Without dropping it
    from sys.modules first, every AppTest after the first would reuse the
    already-imported module without re-registering, and fail with
    "Component ... is not registered." Real production doesn't hit this:
    one server process registers the component once and every browser
    session/rerun shares that same registry -- this reset is purely an
    artifact of exercising multiple independent AppTest instances against
    one shared Python module cache in a single test process.
    """
    sys.modules.pop("search_events", None)
    return AppTest.from_file(str(harness_path), default_timeout=15)


def _write_harness(tmp_path, *, key="test_search", value="", placeholder="", debounce_ms=350):
    harness_path = tmp_path / "harness_app.py"
    harness_path.write_text(
        dedent(
            f"""
            import sys
            sys.path.insert(0, {str(SRC_FOLDER)!r})
            import streamlit as st
            from search_events import search_event_input

            result = search_event_input(
                key={key!r},
                value={value!r},
                placeholder={placeholder!r},
                debounce_ms={debounce_ms!r},
            )
            st.session_state["_result_value"] = result.value
            st.session_state["_result_submitted"] = result.submitted
            """
        ),
        encoding="utf-8",
    )
    return harness_path


class SearchEventInputMountTests(unittest.TestCase):
    def test_mounts_without_exceptions(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            harness_path = _write_harness(Path(tmp_dir))
            at = _fresh_apptest(harness_path)
            at.run()
            self.assertEqual(len(at.exception), 0)

    def test_value_defaults_to_seeded_value_before_any_browser_interaction(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            harness_path = _write_harness(Path(tmp_dir), value="10k resistor")
            at = _fresh_apptest(harness_path)
            at.run()
            self.assertEqual(len(at.exception), 0)
            self.assertEqual(at.session_state["_result_value"], "10k resistor")

    def test_submitted_is_none_on_initial_mount(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            harness_path = _write_harness(Path(tmp_dir))
            at = _fresh_apptest(harness_path)
            at.run()
            self.assertEqual(len(at.exception), 0)
            self.assertIsNone(at.session_state["_result_submitted"])

    def test_second_run_reuses_session_state_value(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            harness_path = _write_harness(Path(tmp_dir), value="")
            at = _fresh_apptest(harness_path)
            at.run()
            at.run()
            self.assertEqual(len(at.exception), 0)
            self.assertEqual(at.session_state["_result_value"], "")


if __name__ == "__main__":
    unittest.main()
