import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from active_bom_state import ActiveBomState
from mouser_cart_client import build_mouser_cart_items
from digikey_mylists_client import build_digikey_mylists_parts
from review_actions import apply_replacement, retry_exact_sourcing
from sourcing_engine import SupplierResult, _supplier_result_to_cache
from supplier_lookup_cache import SupplierLookupCache, build_lookup_key

_OLD_CACHE_ENABLED = None


def setUpModule():
    # retry_exact_sourcing()/apply_replacement() each build their own
    # SupplierLookupCache() when the caller doesn't share one (the normal
    # case for a one-row action). Without disabling it, these tests would
    # read/write the real persistent cache on disk, and reused MPNs like
    # "NEWPART" across tests would leak cached results between them.
    global _OLD_CACHE_ENABLED
    _OLD_CACHE_ENABLED = os.environ.get("SUPPLIER_LOOKUP_CACHE_ENABLED")
    os.environ["SUPPLIER_LOOKUP_CACHE_ENABLED"] = "false"


def tearDownModule():
    if _OLD_CACHE_ENABLED is None:
        os.environ.pop("SUPPLIER_LOOKUP_CACHE_ENABLED", None)
    else:
        os.environ["SUPPLIER_LOOKUP_CACHE_ENABLED"] = _OLD_CACHE_ENABLED


class FakeSupplierClient:
    def __init__(self, result=None, raises=False):
        self.result = result
        self.raises = raises
        self.calls = []

    def find_best_match_for_row(self, row):
        self.calls.append(dict(row))
        if self.raises:
            raise RuntimeError("supplier lookup failed")
        return self.result


def make_state(rows):
    return ActiveBomState(pd.DataFrame(rows), run_id="run-1")


class RetryExactSourcingTests(unittest.TestCase):
    def test_successful_retry_updates_canonical_state_and_result_status(self):
        state = make_state(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "sourcing_status": "check_wall_inventory",
                    "required_qty": "10",
                    "qty_per_board": "10",
                    "build_quantity": "1",
                }
            ]
        )
        mouser = FakeSupplierClient(
            SupplierResult(
                supplier="Mouser",
                manufacturer="Yageo",
                mpn="ABC123",
                stock=500,
                unit_price="0.02",
                supplier_part_number="603-ABC123",
            )
        )
        digikey = FakeSupplierClient(None)

        updated = retry_exact_sourcing(state, "run-1:0", mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(updated["selected_supplier"], "Mouser")
        self.assertEqual(updated["sourcing_status"], "sourced_mouser")
        self.assertEqual(updated["result_status"], "Ready")
        self.assertEqual(updated["source"], "Mouser")
        self.assertEqual(len(mouser.calls), 1)

    def test_retry_skips_digikey_when_mouser_already_covers_requirement(self):
        """Retry must not duplicate/diverge from the shared Mouser-first
        seam: DigiKey is only queried when Mouser doesn't already cover
        the required quantity."""
        state = make_state(
            [{"mpn": "ABC123", "manufacturer": "Yageo", "status": "clean", "required_qty": "10"}]
        )
        mouser = FakeSupplierClient(
            SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="ABC123", stock=500)
        )
        digikey = FakeSupplierClient(
            SupplierResult(supplier="DigiKey", manufacturer="Yageo", mpn="ABC123", stock=500)
        )

        retry_exact_sourcing(state, "run-1:0", mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(len(mouser.calls), 1)
        self.assertEqual(len(digikey.calls), 0)

    def test_retry_falls_back_to_digikey_when_mouser_insufficient(self):
        state = make_state(
            [{"mpn": "ABC123", "manufacturer": "Yageo", "status": "clean", "required_qty": "10"}]
        )
        mouser = FakeSupplierClient(
            SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="ABC123", stock=2)
        )
        digikey = FakeSupplierClient(
            SupplierResult(
                supplier="DigiKey",
                manufacturer="Yageo",
                mpn="ABC123",
                stock=50,
                supplier_part_number="ABC123-ND",
            )
        )

        updated = retry_exact_sourcing(state, "run-1:0", mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(len(digikey.calls), 1)
        self.assertEqual(updated["selected_supplier"], "DigiKey")
        self.assertEqual(updated["sourcing_status"], "sourced_digikey")

    def test_failed_retry_clears_stale_supplier_fields(self):
        state = make_state(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "selected_supplier": "Mouser",
                    "supplier_part_number": "603-STALE",
                    "sourcing_status": "sourced_mouser",
                    "required_qty": "10",
                }
            ]
        )
        mouser = FakeSupplierClient(None)
        digikey = FakeSupplierClient(None)

        updated = retry_exact_sourcing(state, "run-1:0", mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(updated["supplier_part_number"], "")
        self.assertEqual(updated["sourcing_status"], "check_wall_inventory")

    def test_lookup_exception_is_recorded_not_raised(self):
        state = make_state(
            [{"mpn": "ABC123", "manufacturer": "Yageo", "status": "clean", "required_qty": "10"}]
        )
        mouser = FakeSupplierClient(raises=True)
        digikey = FakeSupplierClient(None)

        updated = retry_exact_sourcing(state, "run-1:0", mouser_client=mouser, digikey_client=digikey)

        self.assertIn("Mouser lookup failed", updated["sourcing_notes"])

    def test_unknown_row_id_raises(self):
        state = make_state([{"mpn": "ABC123", "manufacturer": "Yageo", "status": "clean"}])

        with self.assertRaises(KeyError):
            retry_exact_sourcing(
                state, "run-1:999", mouser_client=FakeSupplierClient(), digikey_client=FakeSupplierClient()
            )


def replacement_candidate(source, mpn="NEWPART", manufacturer="Yageo", supplier_part_number="", stock=None):
    return {
        "source": source,
        "mpn": mpn,
        "manufacturer": manufacturer,
        "supplier_part_number": supplier_part_number,
        "unit_price": "",
        "stock": stock,
        "description": "",
        "category": "",
        "package": "",
        "lifecycle_status": "",
        "characteristics": {},
        "raw": {},
    }


def base_row(**overrides):
    row = {
        "mpn": "OLDPART",
        "manufacturer": "Yageo",
        "status": "manual_review",
        "required_qty": "10",
        "qty_per_board": "10",
        "build_quantity": "1",
    }
    row.update(overrides)
    return row


class ApplyReplacementResourcingTests(unittest.TestCase):
    """
    The central Phase 3 correctness fix: apply_replacement() must never
    treat the discovery source as the purchasing supplier. It updates
    component identity, then re-sources through the exact same
    Mouser-first/DigiKey-fallback/no-split seam full-BOM sourcing uses.
    """

    def test_discovered_via_digikey_but_mouser_covers_requirement_is_sourced_from_mouser(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("DigiKey", mpn="NEWPART", supplier_part_number="NEWPART-ND")

        mouser = FakeSupplierClient(
            SupplierResult(
                supplier="Mouser",
                manufacturer="Yageo",
                mpn="NEWPART",
                stock=500,
                supplier_part_number="603-NEWPART",
            )
        )
        digikey = FakeSupplierClient(
            SupplierResult(
                supplier="DigiKey",
                manufacturer="Yageo",
                mpn="NEWPART",
                stock=500,
                supplier_part_number="NEWPART-ND",
            )
        )

        updated = apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        # Discovered via DigiKey, but Mouser can fully cover it -- normal
        # sourcing rules choose Mouser, exactly as they would for any row.
        self.assertEqual(updated["selected_supplier"], "Mouser")
        self.assertEqual(updated["sourcing_status"], "sourced_mouser")
        self.assertEqual(updated["source"], "Mouser")
        self.assertEqual(updated["result_status"], "Ready")
        self.assertEqual(updated["replacement_discovery_source"], "DigiKey")
        # DigiKey is still queried (Mouser-first tries it, but since Mouser
        # covers the requirement first, decide_no_split_supplier picks
        # Mouser) -- the discovery source never short-circuits sourcing.
        self.assertEqual(len(mouser.calls), 1)

    def test_discovered_via_mouser_but_mouser_shortage_falls_back_to_digikey(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("Mouser", mpn="NEWPART")

        mouser = FakeSupplierClient(
            SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="NEWPART", stock=3)
        )
        digikey = FakeSupplierClient(
            SupplierResult(
                supplier="DigiKey",
                manufacturer="Yageo",
                mpn="NEWPART",
                stock=50,
                supplier_part_number="NEWPART-ND",
            )
        )

        updated = apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(updated["selected_supplier"], "DigiKey")
        self.assertEqual(updated["sourcing_status"], "sourced_digikey")
        self.assertEqual(updated["supplier_part_number"], "NEWPART-ND")

    def test_both_suppliers_short_stays_needs_review_not_ready(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("Mouser", mpn="NEWPART")

        mouser = FakeSupplierClient(
            SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="NEWPART", stock=2)
        )
        digikey = FakeSupplierClient(
            SupplierResult(supplier="DigiKey", manufacturer="Yageo", mpn="NEWPART", stock=1)
        )

        updated = apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(updated["selected_supplier"], "")
        self.assertEqual(updated["sourcing_status"], "check_wall_inventory")
        self.assertEqual(updated["result_status"], "Needs Review")
        self.assertTrue(updated["needs_review"])

    def test_supplier_api_failure_does_not_mark_ready(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("Mouser", mpn="NEWPART")

        mouser = FakeSupplierClient(raises=True)
        digikey = FakeSupplierClient(raises=True)

        updated = apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        self.assertNotEqual(updated["result_status"], "Ready")
        self.assertIn("lookup failed", updated["sourcing_notes"])

    def test_missing_required_quantity_does_not_mark_ready(self):
        state = make_state([base_row(required_qty="")])
        candidate = replacement_candidate("Mouser", mpn="NEWPART")

        mouser = FakeSupplierClient(
            SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="NEWPART", stock=500)
        )
        digikey = FakeSupplierClient(None)

        updated = apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        self.assertNotEqual(updated["result_status"], "Ready")
        self.assertEqual(updated["sourcing_status"], "manual_review")

    def test_supplier_order_qty_is_recalculated_for_the_new_component(self):
        state = make_state([base_row(qty_per_board="3", build_quantity="4", required_qty="12")])
        candidate = replacement_candidate("Mouser", mpn="NEWPART")
        mouser = FakeSupplierClient(
            SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="NEWPART", stock=500)
        )
        digikey = FakeSupplierClient(None)

        updated = apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(updated["supplier_order_qty"], "12")

    def test_mouser_replacement_reenters_cart_pipeline(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("Mouser", mpn="NEWPART")
        mouser = FakeSupplierClient(
            SupplierResult(
                supplier="Mouser",
                manufacturer="Yageo",
                mpn="NEWPART",
                stock=500,
                supplier_part_number="603-NEWPART",
            )
        )
        digikey = FakeSupplierClient(None)

        apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        cart_items = build_mouser_cart_items(state.dataframe)
        self.assertEqual(len(cart_items), 1)
        self.assertEqual(cart_items[0]["MouserPartNumber"], "603-NEWPART")

    def test_digikey_replacement_reenters_mylists_pipeline(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("DigiKey", mpn="NEWPART-DK")
        mouser = FakeSupplierClient(SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="NEWPART-DK", stock=1))
        digikey = FakeSupplierClient(
            SupplierResult(
                supplier="DigiKey",
                manufacturer="Yageo",
                mpn="NEWPART-DK",
                stock=200,
                supplier_part_number="NEWPART-DK-ND",
            )
        )

        apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        parts = build_digikey_mylists_parts(state.dataframe)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["RequestedPartNumber"], "NEWPART-DK-ND")

    def test_shortage_replacement_is_excluded_from_purchasing_builders(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("Mouser", mpn="NEWPART")
        mouser = FakeSupplierClient(SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="NEWPART", stock=1))
        digikey = FakeSupplierClient(SupplierResult(supplier="DigiKey", manufacturer="Yageo", mpn="NEWPART", stock=1))

        apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(build_mouser_cart_items(state.dataframe), [])
        self.assertEqual(build_digikey_mylists_parts(state.dataframe), [])

    def test_replacement_regenerates_review_status_from_canonical_state(self):
        state = make_state([base_row(mpn="", status="missing_mpn", notes="missing mpn")])
        self.assertEqual(len(state.review_items()), 1)

        candidate = replacement_candidate("Mouser", mpn="FOUND123")
        mouser = FakeSupplierClient(SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="FOUND123", stock=500))
        digikey = FakeSupplierClient(None)

        apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(state.review_items(), [])

    def test_unknown_row_id_raises(self):
        state = make_state([base_row()])

        with self.assertRaises(KeyError):
            apply_replacement(state, "run-1:999", replacement_candidate("Mouser"))


class ApplyReplacementPartsBoxTests(unittest.TestCase):
    def test_partsbox_replacement_clears_old_external_supplier_state(self):
        state = make_state(
            [
                base_row(
                    selected_supplier="Mouser",
                    supplier_part_number="OLD-MOUSER-PN",
                    sourcing_status="sourced_mouser",
                )
            ]
        )
        candidate = replacement_candidate("PartsBox", mpn="NEWPART-PB")
        candidate["raw"] = {"part/id": "part-999"}

        # No external match found for the new identity.
        mouser = FakeSupplierClient(None)
        digikey = FakeSupplierClient(None)

        updated = apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        self.assertNotEqual(updated["selected_supplier"], "Mouser")
        self.assertNotEqual(updated["supplier_part_number"], "OLD-MOUSER-PN")
        self.assertEqual(updated["partsbox_match_status"], "matched")
        self.assertEqual(updated["partsbox_part_id"], "part-999")

    def test_partsbox_match_alone_does_not_claim_ready(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("PartsBox", mpn="NEWPART-PB")
        candidate["raw"] = {"part/id": "part-999"}

        mouser = FakeSupplierClient(None)
        digikey = FakeSupplierClient(None)

        updated = apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        # A PartsBox match is internal inventory info, not confirmed
        # external purchase readiness -- without a real supplier match,
        # this must not be Ready.
        self.assertEqual(updated["partsbox_match_status"], "matched")
        self.assertNotEqual(updated["result_status"], "Ready")

    def test_partsbox_replacement_still_attempts_external_sourcing_and_can_be_ready(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("PartsBox", mpn="NEWPART-PB")
        candidate["raw"] = {"part/id": "part-999"}

        mouser = FakeSupplierClient(
            SupplierResult(
                supplier="Mouser",
                manufacturer="Yageo",
                mpn="NEWPART-PB",
                stock=500,
                supplier_part_number="603-NEWPART-PB",
            )
        )
        digikey = FakeSupplierClient(None)

        updated = apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        # Both facts survive: internally matched in PartsBox AND
        # confirmed externally purchasable from Mouser.
        self.assertEqual(updated["partsbox_match_status"], "matched")
        self.assertEqual(updated["selected_supplier"], "Mouser")
        self.assertEqual(updated["source"], "Mouser")
        self.assertEqual(updated["result_status"], "Ready")


class SourceSelectionGatingTests(unittest.TestCase):
    """
    The authoritative Sources selection (the same state governing Main
    Search and uploads) must also govern Retry Exact and replacement
    re-sourcing -- an unchecked supplier must never be queried by either
    seam, not merely excluded from the purchasing decision. Confirmed
    directly against FakeSupplierClient.calls, not just the resulting
    sourcing_status.
    """

    def test_retry_exact_with_mouser_only_never_calls_digikey(self):
        state = make_state(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "sourcing_status": "check_wall_inventory",
                    "required_qty": "10",
                    "qty_per_board": "10",
                    "build_quantity": "1",
                }
            ]
        )
        mouser = FakeSupplierClient(
            SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="ABC123", stock=50, supplier_part_number="603-ABC")
        )
        digikey = FakeSupplierClient(None)

        retry_exact_sourcing(
            state, "run-1:0", mouser_client=mouser, digikey_client=digikey, sources=frozenset({"mouser"})
        )

        self.assertEqual(len(mouser.calls), 1)
        self.assertEqual(len(digikey.calls), 0)

    def test_retry_exact_with_digikey_only_never_calls_mouser(self):
        state = make_state(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "sourcing_status": "check_wall_inventory",
                    "required_qty": "10",
                    "qty_per_board": "10",
                    "build_quantity": "1",
                }
            ]
        )
        mouser = FakeSupplierClient(None)
        digikey = FakeSupplierClient(
            SupplierResult(supplier="DigiKey", manufacturer="Yageo", mpn="ABC123", stock=50, supplier_part_number="296-ABC")
        )

        retry_exact_sourcing(
            state, "run-1:0", mouser_client=mouser, digikey_client=digikey, sources=frozenset({"digikey"})
        )

        self.assertEqual(len(mouser.calls), 0)
        self.assertEqual(len(digikey.calls), 1)

    def test_retry_exact_with_neither_supplier_selected_calls_neither(self):
        state = make_state(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "sourcing_status": "check_wall_inventory",
                    "required_qty": "10",
                    "qty_per_board": "10",
                    "build_quantity": "1",
                }
            ]
        )
        mouser = FakeSupplierClient(None)
        digikey = FakeSupplierClient(None)

        result = retry_exact_sourcing(
            state, "run-1:0", mouser_client=mouser, digikey_client=digikey, sources=frozenset()
        )

        self.assertEqual(len(mouser.calls), 0)
        self.assertEqual(len(digikey.calls), 0)
        self.assertEqual(result["sourcing_status"], "check_wall_inventory")

    def test_apply_replacement_with_mouser_only_never_calls_digikey(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("DigiKey", mpn="NEWPART")
        mouser = FakeSupplierClient(
            SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="NEWPART", stock=50, supplier_part_number="603-NEWPART")
        )
        digikey = FakeSupplierClient(None)

        apply_replacement(
            state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey, sources=frozenset({"mouser"})
        )

        self.assertEqual(len(mouser.calls), 1)
        self.assertEqual(len(digikey.calls), 0)

    def test_apply_replacement_default_sources_is_backward_compatible(self):
        """
        Omitting `sources` entirely (every pre-existing caller) must
        still query both suppliers, exactly as before this parameter
        was added.
        """
        state = make_state([base_row()])  # required_qty="10"
        candidate = replacement_candidate("Mouser", mpn="NEWPART")
        # Mouser stock (2) is short of required_qty (10) -- DigiKey must
        # still be consulted as a fallback when sources isn't restricted.
        mouser = FakeSupplierClient(
            SupplierResult(supplier="Mouser", manufacturer="Yageo", mpn="NEWPART", stock=2, supplier_part_number="603-NEWPART")
        )
        digikey = FakeSupplierClient(None)

        apply_replacement(state, "run-1:0", candidate, mouser_client=mouser, digikey_client=digikey)

        self.assertEqual(len(mouser.calls), 1)
        self.assertEqual(len(digikey.calls), 1)


class PopulatedCacheSourceSelectionGatingTests(unittest.TestCase):
    """
    Test E from
    Documentation/AutoBOM_Disabled_Supplier_Cache_Bypass_Correction_Report.md:
    SourceSelectionGatingTests above proves gating with the persistent
    cache disabled entirely, which cannot reproduce the original defect
    (a stale cached result for a supplier the operator just unchecked).
    These tests enable a real, populated persistent cache -- since
    retry_exact_sourcing()/apply_replacement() build their own
    SupplierLookupCache() per call, the prepopulated entry must be saved
    to disk at the path they'll read from.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autobom_review_actions_cache_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self._old_env = {
            "SUPPLIER_LOOKUP_CACHE_ENABLED": os.environ.get("SUPPLIER_LOOKUP_CACHE_ENABLED"),
            "SUPPLIER_LOOKUP_CACHE_PATH": os.environ.get("SUPPLIER_LOOKUP_CACHE_PATH"),
        }
        os.environ["SUPPLIER_LOOKUP_CACHE_ENABLED"] = "true"
        os.environ["SUPPLIER_LOOKUP_CACHE_PATH"] = str(self.temp_dir / "supplier_lookup_cache.json")
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, old_value in self._old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

    def _seed_mouser_cache(self, row, result):
        cache = SupplierLookupCache()
        key = build_lookup_key("mouser", row)
        cache.set(key, _supplier_result_to_cache(result))
        cache.save()

    def test_retry_exact_with_digikey_only_ignores_a_stale_cached_mouser_result(self):
        state = make_state(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "sourcing_status": "check_wall_inventory",
                    "required_qty": "10",
                    "qty_per_board": "10",
                    "build_quantity": "1",
                    "supplier_part_number": "",
                }
            ]
        )
        self._seed_mouser_cache(
            {"mpn": "ABC123", "manufacturer": "Yageo", "supplier_part_number": ""},
            SupplierResult(
                supplier="Mouser", manufacturer="Yageo", mpn="ABC123", stock=500,
                supplier_part_number="603-STALE-CACHED",
            ),
        )
        digikey = FakeSupplierClient(
            SupplierResult(
                supplier="DigiKey", manufacturer="Yageo", mpn="ABC123", stock=50,
                supplier_part_number="ABC123-ND",
            )
        )

        updated = retry_exact_sourcing(
            state, "run-1:0", digikey_client=digikey, sources=frozenset({"digikey"})
        )

        self.assertEqual(updated["selected_supplier"], "DigiKey")
        self.assertEqual(updated["sourcing_status"], "sourced_digikey")
        self.assertNotEqual(updated["supplier_part_number"], "603-STALE-CACHED")

    def test_apply_replacement_with_digikey_only_ignores_a_stale_cached_mouser_result(self):
        state = make_state([base_row()])
        candidate = replacement_candidate("DigiKey", mpn="NEWPART")
        self._seed_mouser_cache(
            {"mpn": "NEWPART", "manufacturer": "Yageo", "supplier_part_number": ""},
            SupplierResult(
                supplier="Mouser", manufacturer="Yageo", mpn="NEWPART", stock=500,
                supplier_part_number="603-STALE-CACHED",
            ),
        )
        digikey = FakeSupplierClient(
            SupplierResult(
                supplier="DigiKey", manufacturer="Yageo", mpn="NEWPART", stock=50,
                supplier_part_number="NEWPART-ND",
            )
        )

        updated = apply_replacement(
            state, "run-1:0", candidate, digikey_client=digikey, sources=frozenset({"digikey"})
        )

        self.assertNotEqual(updated["selected_supplier"], "Mouser")
        self.assertEqual(updated["selected_supplier"], "DigiKey")
        self.assertNotEqual(updated["supplier_part_number"], "603-STALE-CACHED")


if __name__ == "__main__":
    unittest.main()
