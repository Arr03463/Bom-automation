import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

import partsbox_inventory
from partsbox_inventory import (
    build_partsbox_inventory_snapshot,
    get_snapshot,
    invalidate,
    net_quantities_by_storage,
    peek_snapshot,
    refresh,
    reset_cache_for_tests,
)

STORAGE_C1 = {"storage/id": "s-c1", "storage/name": "C1 - Resistors"}
STORAGE_PROJECT = {"storage/id": "s-dab", "storage/name": "DAB Prototype", "storage/tags": ["production"]}
PROJECT_DAB = {"project/name": "DAB Prototype"}


def _ledger(*entries):
    return [{"stock/quantity": qty, "stock/storage-id": storage_id} for storage_id, qty in entries]


class FakePartsBoxClient:
    def __init__(self, parts=None, storage_locations=None, projects=None, calls=None):
        self.parts = parts or []
        self.storage_locations = storage_locations or [STORAGE_C1]
        self.projects = projects or []
        self.calls = calls if calls is not None else []

    def get_parts(self):
        self.calls.append("part/all")
        return self.parts

    def list_storage_locations(self):
        self.calls.append("storage/all")
        return {"data": self.storage_locations}

    def list_projects(self):
        self.calls.append("project/all")
        return {"data": self.projects}


class NetQuantitiesByStorageTests(unittest.TestCase):
    def test_sums_signed_entries_per_storage(self):
        ledger = _ledger(("s1", 10), ("s1", -3), ("s2", 5))
        self.assertEqual(net_quantities_by_storage(ledger), {"s1": 7, "s2": 5})

    def test_drops_zero_and_negative_totals(self):
        ledger = _ledger(("s1", 10), ("s1", -10), ("s2", 5), ("s2", -8))
        self.assertEqual(net_quantities_by_storage(ledger), {})

    def test_non_list_input_returns_empty(self):
        self.assertEqual(net_quantities_by_storage(None), {})
        self.assertEqual(net_quantities_by_storage("not a ledger"), {})

    def test_malformed_entries_are_skipped_not_raising(self):
        ledger = [{"stock/quantity": 5, "stock/storage-id": "s1"}, "not a dict", {"stock/quantity": "bad"}]
        self.assertEqual(net_quantities_by_storage(ledger), {"s1": 5})


class BuildSnapshotTests(unittest.TestCase):
    def test_joins_part_storage_and_project_data(self):
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/id": "p1",
                    "part/mpn": "RC0603FR-0710KL",
                    "part/manufacturer": "Yageo",
                    "part/description": "10k Resistor",
                    "part/stock": _ledger(("s-c1", 100)),
                }
            ],
            storage_locations=[STORAGE_C1],
        )

        snapshot = build_partsbox_inventory_snapshot(client=client)

        self.assertEqual(snapshot.part_count, 1)
        self.assertEqual(snapshot.storage_count, 1)
        part = snapshot.parts[0]
        self.assertEqual(part.mpn, "RC0603FR-0710KL")
        self.assertEqual(part.total_quantity, 100)
        self.assertEqual(len(part.locations), 1)
        self.assertEqual(part.locations[0]["name"], "C1 - Resistors")

    def test_part_can_have_multiple_simultaneous_locations(self):
        """
        Confirmed against the operator-supplied export: a part must be
        able to appear in more than one current location at once (e.g.
        general Development storage AND a Project) -- never collapsed
        into one location field.
        """
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "MULTI123",
                    "part/manufacturer": "Yageo",
                    "part/stock": _ledger(("s-c1", 40), ("s-dab", 12)),
                }
            ],
            storage_locations=[STORAGE_C1, STORAGE_PROJECT],
            projects=[PROJECT_DAB],
        )

        snapshot = build_partsbox_inventory_snapshot(client=client)
        part = snapshot.parts[0]

        self.assertEqual(len(part.locations), 2)
        self.assertEqual(part.total_quantity, 52)
        location_names = {loc["name"] for loc in part.locations}
        self.assertEqual(location_names, {"C1 - Resistors", "DAB Prototype"})

    def test_locations_split_by_classification(self):
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "SPLIT1",
                    "part/manufacturer": "Yageo",
                    "part/stock": _ledger(("s-c1", 40), ("s-dab", 12)),
                }
            ],
            storage_locations=[STORAGE_C1, STORAGE_PROJECT],
            projects=[PROJECT_DAB],
        )

        snapshot = build_partsbox_inventory_snapshot(client=client)
        part = snapshot.parts[0]

        self.assertEqual(len(part.development_locations), 1)
        self.assertEqual(part.development_locations[0]["name"], "C1 - Resistors")
        self.assertEqual(len(part.project_locations), 1)
        self.assertEqual(part.project_locations[0]["name"], "DAB Prototype")
        self.assertEqual(part.projects, ["DAB Prototype"])

    def test_zero_and_negative_ledger_totals_do_not_produce_a_location(self):
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "GONE123",
                    "part/manufacturer": "Yageo",
                    "part/stock": _ledger(("s-c1", 10), ("s-c1", -10)),
                }
            ],
            storage_locations=[STORAGE_C1],
        )

        snapshot = build_partsbox_inventory_snapshot(client=client)
        part = snapshot.parts[0]

        self.assertEqual(part.locations, [])
        self.assertEqual(part.total_quantity, 0)

    def test_characteristics_preserve_unrecognized_fields(self):
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "CHARTEST",
                    "part/manufacturer": "Yageo",
                    "part/voltage": "25V",
                }
            ],
        )

        snapshot = build_partsbox_inventory_snapshot(client=client)
        self.assertEqual(snapshot.parts[0].characteristics.get("voltage"), "25V")

    def test_raw_record_is_preserved(self):
        raw_part = {"part/mpn": "RAWKEEP", "part/manufacturer": "Yageo", "part/custom-field": "x"}
        client = FakePartsBoxClient(parts=[raw_part])

        snapshot = build_partsbox_inventory_snapshot(client=client)
        self.assertIs(snapshot.parts[0].raw, raw_part)

    def test_each_required_endpoint_called_exactly_once(self):
        client = FakePartsBoxClient(parts=[{"part/mpn": "A", "part/manufacturer": "Y"}])

        build_partsbox_inventory_snapshot(client=client)

        self.assertEqual(client.calls.count("part/all"), 1)
        self.assertEqual(client.calls.count("storage/all"), 1)
        self.assertEqual(client.calls.count("project/all"), 1)


class InventoryPartToDictTests(unittest.TestCase):
    """
    to_dict() is what feeds record_filter.search_and_filter()/
    generate_facets() and the shared Selected Part Details panel -- it
    must look like the same flat shape component_lookup.LookupResult.to_dict()
    produces for Mouser/DigiKey/plain-PartsBox results (source/mpn/
    manufacturer/stock/...), plus list-valued location/storage_space/
    project fields record_filter's membership-filter kind expects.
    """

    def _build_multi_location_part(self):
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/id": "p1",
                    "part/mpn": "MULTI123",
                    "part/manufacturer": "Yageo",
                    "part/description": "10k Resistor",
                    "part/voltage": "25V",
                    "part/stock": _ledger(("s-c1", 40), ("s-dab", 12)),
                }
            ],
            storage_locations=[STORAGE_C1, STORAGE_PROJECT],
            projects=[PROJECT_DAB],
        )
        snapshot = build_partsbox_inventory_snapshot(client=client)
        return snapshot.parts[0]

    def test_to_dict_has_the_shared_flat_shape(self):
        part = self._build_multi_location_part()
        data = part.to_dict()

        self.assertEqual(data["source"], "PartsBox")
        self.assertEqual(data["mpn"], "MULTI123")
        self.assertEqual(data["manufacturer"], "Yageo")
        self.assertEqual(data["stock"], 52)  # net ledger total, not None
        self.assertEqual(set(data["location"]), {"C1 - Resistors", "DAB Prototype"})
        self.assertEqual(set(data["storage_space"]), {"Development", "Project"})
        self.assertEqual(data["project"], ["DAB Prototype"])

    def test_characteristics_are_flattened_onto_the_top_level(self):
        part = self._build_multi_location_part()
        data = part.to_dict()
        self.assertEqual(data["voltage"], "25V")

    def test_to_dict_is_compatible_with_record_filter_membership_filtering(self):
        import record_filter

        part = self._build_multi_location_part()
        results = [part.to_dict()]

        matched = record_filter.apply_filters(results, {"storage_space": ["Development"]})
        self.assertEqual(len(matched), 1)

        unmatched = record_filter.apply_filters(results, {"storage_space": ["Mechanical"]})
        self.assertEqual(unmatched, [])


class SnapshotCacheTests(unittest.TestCase):
    def setUp(self):
        reset_cache_for_tests()
        self.addCleanup(reset_cache_for_tests)

    def test_get_snapshot_fetches_once_and_reuses_within_ttl(self):
        client = FakePartsBoxClient(parts=[{"part/mpn": "A", "part/manufacturer": "Y"}])

        first = get_snapshot(ttl_seconds=300, client=client)
        second = get_snapshot(ttl_seconds=300, client=client)

        self.assertIs(first, second)
        self.assertEqual(client.calls.count("part/all"), 1)

    def test_expired_ttl_triggers_a_fresh_fetch(self):
        client = FakePartsBoxClient(parts=[{"part/mpn": "A", "part/manufacturer": "Y"}])
        first = get_snapshot(ttl_seconds=300, client=client)

        with patch("time.time", return_value=time.time() + 301):
            second = get_snapshot(ttl_seconds=300, client=client)

        self.assertIsNot(first, second)
        self.assertEqual(client.calls.count("part/all"), 2)

    def test_force_refresh_always_fetches(self):
        client = FakePartsBoxClient(parts=[{"part/mpn": "A", "part/manufacturer": "Y"}])
        get_snapshot(ttl_seconds=300, client=client)
        get_snapshot(ttl_seconds=300, force_refresh=True, client=client)

        self.assertEqual(client.calls.count("part/all"), 2)

    def test_refresh_increments_generation(self):
        client = FakePartsBoxClient(parts=[{"part/mpn": "A", "part/manufacturer": "Y"}])
        first = refresh(client=client)
        second = refresh(client=client)

        self.assertEqual(second.generation, first.generation + 1)

    def test_invalidate_forces_next_get_snapshot_to_refetch(self):
        client = FakePartsBoxClient(parts=[{"part/mpn": "A", "part/manufacturer": "Y"}])
        get_snapshot(ttl_seconds=300, client=client)
        invalidate()
        get_snapshot(ttl_seconds=300, client=client)

        self.assertEqual(client.calls.count("part/all"), 2)

    def test_peek_snapshot_does_not_trigger_a_fetch(self):
        client = FakePartsBoxClient(parts=[{"part/mpn": "A", "part/manufacturer": "Y"}])
        self.assertIsNone(peek_snapshot())
        self.assertEqual(client.calls, [])

        get_snapshot(ttl_seconds=300, client=client)
        self.assertIsNotNone(peek_snapshot())

    def test_failed_refresh_keeps_serving_the_previous_snapshot(self):
        good_client = FakePartsBoxClient(parts=[{"part/mpn": "A", "part/manufacturer": "Y"}])
        good = get_snapshot(ttl_seconds=300, client=good_client)

        class FailingClient:
            def get_parts(self):
                raise RuntimeError("PartsBox is down")

            def list_storage_locations(self):
                return {"data": []}

            def list_projects(self):
                return {"data": []}

        with patch("time.time", return_value=time.time() + 301):
            served = get_snapshot(ttl_seconds=300, client=FailingClient())

        self.assertIs(served, good)

    def test_refresh_raises_on_failure_without_touching_cache(self):
        good_client = FakePartsBoxClient(parts=[{"part/mpn": "A", "part/manufacturer": "Y"}])
        get_snapshot(ttl_seconds=300, client=good_client)

        class FailingClient:
            def get_parts(self):
                raise RuntimeError("PartsBox is down")

            def list_storage_locations(self):
                return {"data": []}

            def list_projects(self):
                return {"data": []}

        with self.assertRaises(RuntimeError):
            refresh(client=FailingClient())

        # The good snapshot from before is still being served.
        self.assertIsNotNone(peek_snapshot())


if __name__ == "__main__":
    unittest.main()
