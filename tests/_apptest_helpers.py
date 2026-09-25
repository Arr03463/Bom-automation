"""
Shared helper for tests that build more than one streamlit.testing.v1.AppTest
instance against app.py within a single test process.

AppTest runs without a real Streamlit Runtime ("bare mode"). Custom
Components v2's get_bidi_component_manager() only returns a stable,
shared registry when a real Runtime exists (see
streamlit/components/v2/get_bidi_component_manager.py); in bare mode it
hands back a brand-new, empty BidiComponentManager on every call. app.py
registers search_events.py's component once, at import time -- fine for
one AppTest, but a SECOND independent AppTest.from_file("app.py") call
in the same process finds `search_events` already cached in
sys.modules, so its module-level `st.components.v2.component(...)` call
never re-executes and never registers against the second AppTest's own
(new, empty) bare-mode manager, raising "Component ... is not
registered." Real production is unaffected: a live `streamlit run`
process has exactly one real Runtime, so every session/rerun shares the
same registry the component registered against on first import --
confirmed directly against the installed package (see the Phase M
implementation report). Popping `search_events` from sys.modules before
each fresh AppTest forces its registration to re-run for that AppTest's
own context, matching what a real Streamlit process does implicitly by
only ever having one such context to register against.
"""

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
APP_PATH = PROJECT_ROOT / "app.py"

if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from partsbox_inventory import reset_cache_for_tests as _reset_partsbox_snapshot_cache


def fresh_app_test(default_timeout=15):
    """
    Besides the component-registry reset (see the module docstring),
    also drops the process-wide PartsBox snapshot cache
    (partsbox_inventory.py's module-level dict) so one test's mocked/
    fake snapshot can never leak into a later test as a seemingly
    "already warm" cache -- Main Search only fetches PartsBox when a
    search is typed or the cache is already warm (see
    render_component_search_intake()'s should_load_partsbox), so a
    leaked fake snapshot from a prior test would silently make a
    "blank startup" test see PartsBox data it never asked for.
    """
    sys.modules.pop("search_events", None)
    _reset_partsbox_snapshot_cache()
    return AppTest.from_file(str(APP_PATH), default_timeout=default_timeout)
