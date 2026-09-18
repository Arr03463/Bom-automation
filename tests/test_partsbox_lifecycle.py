import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from partsbox_project_builder import (
    add_bom_entries_to_project,
    build_project_entries,
    create_partsbox_project_and_storage,
)


PARTS = [
    {"part/id": "part-abc", "part/mpn": "ABC123", "part/manufacturer": "Yageo"},
    {"part/id": "part-xyz", "part/mpn": "XYZ789", "part/manufacturer": "TI"},
]

_UNSET = object()


class FakePartsBoxClient:
    """Stand-in for PartsBoxClient with no network calls, for lifecycle tests."""

    def __init__(
        self,
        parts=None,
        existing_project=None,
        existing_storage=None,
        existing_entries=None,
        raw_existing_entries_response=_UNSET,
    ):
        self.parts = parts or []
        self.existing_project = existing_project
        self.existing_storage = existing_storage
        self.existing_entries = existing_entries if existing_entries is not None else []
        # When set, returned verbatim from get_project_entries() instead of
        # the normal {"data": existing_entries} envelope -- lets tests
        # simulate malformed/unrecognized PartsBox response shapes.
        self.raw_existing_entries_response = raw_existing_entries_response
        self.create_project_calls = []
        self.create_storage_calls = []
        self.add_entries_calls = []
        self.get_entries_calls = []

    def find_part_by_mpn_and_manufacturer(self, mpn, manufacturer=""):
        target_mpn = str(mpn or "").strip().lower()
        for part in self.parts:
            if str(part.get("part/mpn", "")).strip().lower() == target_mpn:
                return part
        return None

    def find_project_by_name(self, name):
        return self.existing_project

    def find_storage_by_name(self, name):
        return self.existing_storage

    def create_project(self, name, description=""):
        self.create_project_calls.append({"name": name, "description": description})
        return {"project/id": "proj-new", "project/name": name}

    def create_storage_location(self, name, description="", tags=None):
        self.create_storage_calls.append({"name": name, "description": description, "tags": tags})
        return {"storage/id": "storage-new", "storage/name": name, "storage/tags": tags or []}

    def get_project_entries(self, project_id):
        self.get_entries_calls.append(project_id)
        if self.raw_existing_entries_response is not _UNSET:
            return self.raw_existing_entries_response
        return {"data": self.existing_entries}

    def add_project_entries(self, project_id, entries):
        self.add_entries_calls.append({"project_id": project_id, "entries": entries})
        return {"status": "ok"}


def make_bom():
    return pd.DataFrame(
        [
            {
                "mpn": "ABC123",
                "manufacturer": "Yageo",
                "description": "10uF Cap",
                "designators": "C1, C2",
                "qty_per_board": "2",
            },
            {
                "mpn": "XYZ789",
                "manufacturer": "TI",
                "description": "Op Amp",
                "designators": "U1",
                "qty_per_board": "1",
            },
        ]
    )


class PartsBoxEntryIdempotencyTests(unittest.TestCase):
    def test_first_run_adds_all_entries(self):
        client = FakePartsBoxClient(parts=PARTS, existing_entries=[])
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, make_bom(), client=client)

        self.assertEqual(result["entries_added"], 2)
        self.assertEqual(result["entries_skipped_existing"], 0)
        self.assertEqual(len(client.add_entries_calls), 1)
        self.assertEqual(len(client.add_entries_calls[0]["entries"]), 2)

    def test_repeat_run_unchanged_bom_adds_nothing(self):
        clean_bom = make_bom()
        existing_entries, _ = build_project_entries(clean_bom, FakePartsBoxClient(parts=PARTS))

        client = FakePartsBoxClient(parts=PARTS, existing_entries=existing_entries)
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, clean_bom, client=client)

        self.assertEqual(result["entries_added"], 0)
        self.assertEqual(result["entries_skipped_existing"], 2)
        self.assertEqual(client.add_entries_calls, [])

    def test_repeat_run_with_new_row_only_adds_missing_entry(self):
        original_bom = make_bom()
        existing_entries, _ = build_project_entries(original_bom, FakePartsBoxClient(parts=PARTS))

        updated_bom = pd.concat(
            [
                original_bom,
                pd.DataFrame(
                    [
                        {
                            "mpn": "NEW111",
                            "manufacturer": "Murata",
                            "description": "New part",
                            "designators": "R5",
                            "qty_per_board": "3",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

        parts_with_new = PARTS + [{"part/id": "part-new", "part/mpn": "NEW111", "part/manufacturer": "Murata"}]
        client = FakePartsBoxClient(parts=parts_with_new, existing_entries=existing_entries)
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, updated_bom, client=client)

        self.assertEqual(result["entries_added"], 1)
        self.assertEqual(result["entries_skipped_existing"], 2)
        self.assertEqual(len(client.add_entries_calls), 1)
        self.assertEqual(len(client.add_entries_calls[0]["entries"]), 1)
        self.assertEqual(client.add_entries_calls[0]["entries"][0]["entry/part-id"], "part-new")

    def test_missing_project_id_skips_without_calling_get_entries(self):
        client = FakePartsBoxClient(parts=PARTS)

        result = add_bom_entries_to_project(
            {"project_result": {"dry_run": True}}, make_bom(), client=client
        )

        self.assertTrue(result["skipped"])
        self.assertEqual(client.get_entries_calls, [])
        self.assertEqual(client.add_entries_calls, [])

    def test_valid_empty_project_response_proceeds(self):
        client = FakePartsBoxClient(parts=PARTS, existing_entries=[])
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, make_bom(), client=client)

        self.assertFalse(result["skipped"])
        self.assertEqual(result["entries_added"], 2)
        self.assertEqual(result["quantity_mismatches"], [])

    def test_malformed_response_fails_closed(self):
        client = FakePartsBoxClient(
            parts=PARTS, raw_existing_entries_response={"data": "not-a-list"}
        )
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, make_bom(), client=client)

        self.assertTrue(result["skipped"])
        self.assertTrue(result.get("unrecognized_response"))
        self.assertEqual(client.add_entries_calls, [])

    def test_unknown_envelope_fails_closed(self):
        client = FakePartsBoxClient(
            parts=PARTS,
            raw_existing_entries_response={"partsbox.status/category": "ok"},
        )
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, make_bom(), client=client)

        self.assertTrue(result["skipped"])
        self.assertTrue(result.get("unrecognized_response"))
        self.assertEqual(client.add_entries_calls, [])

    def test_non_dict_response_fails_closed(self):
        client = FakePartsBoxClient(parts=PARTS, raw_existing_entries_response=["unexpected"])
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, make_bom(), client=client)

        self.assertTrue(result["skipped"])
        self.assertTrue(result.get("unrecognized_response"))
        self.assertEqual(client.add_entries_calls, [])

    def test_changed_quantity_is_flagged_not_duplicated_or_silently_synced(self):
        original_bom = make_bom()
        existing_entries, _ = build_project_entries(original_bom, FakePartsBoxClient(parts=PARTS))

        updated_bom = original_bom.copy()
        updated_bom.loc[0, "qty_per_board"] = "5"  # was 2

        client = FakePartsBoxClient(parts=PARTS, existing_entries=existing_entries)
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, updated_bom, client=client)

        self.assertEqual(result["entries_added"], 0)
        self.assertEqual(client.add_entries_calls, [])
        self.assertEqual(len(result["quantity_mismatches"]), 1)
        mismatch = result["quantity_mismatches"][0]
        self.assertEqual(mismatch["existing_quantity"], 2)
        self.assertEqual(mismatch["intended_quantity"], 5)

    def test_reordered_designators_are_still_recognized_as_same_entry(self):
        original_bom = make_bom()
        existing_entries, _ = build_project_entries(original_bom, FakePartsBoxClient(parts=PARTS))

        updated_bom = original_bom.copy()
        updated_bom.loc[0, "designators"] = "C2, C1"  # reordered from "C1, C2"

        client = FakePartsBoxClient(parts=PARTS, existing_entries=existing_entries)
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, updated_bom, client=client)

        self.assertEqual(result["entries_added"], 0)
        self.assertEqual(result["entries_skipped_existing"], 2)
        self.assertEqual(result["quantity_mismatches"], [])

    def test_same_part_different_designators_is_treated_as_new_entry(self):
        original_bom = make_bom()
        existing_entries, _ = build_project_entries(original_bom, FakePartsBoxClient(parts=PARTS))

        updated_bom = pd.concat(
            [
                original_bom,
                pd.DataFrame(
                    [
                        {
                            "mpn": "ABC123",
                            "manufacturer": "Yageo",
                            "description": "10uF Cap",
                            "designators": "C3, C4",
                            "qty_per_board": "2",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

        client = FakePartsBoxClient(parts=PARTS, existing_entries=existing_entries)
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, updated_bom, client=client)

        self.assertEqual(result["entries_added"], 1)
        self.assertEqual(result["entries_skipped_existing"], 2)
        self.assertEqual(result["quantity_mismatches"], [])
        self.assertEqual(
            client.add_entries_calls[0]["entries"][0]["entry/designators"], ["C3", "C4"]
        )

    def test_missing_part_id_falls_back_to_name_identity(self):
        bom = pd.DataFrame(
            [
                {
                    "mpn": "UNKNOWN999",
                    "manufacturer": "Foo",
                    "description": "Some part",
                    "designators": "R9",
                    "qty_per_board": "3",
                }
            ]
        )
        existing_entries, _ = build_project_entries(bom, FakePartsBoxClient(parts=PARTS))
        self.assertNotIn("entry/part-id", existing_entries[0])

        client = FakePartsBoxClient(parts=PARTS, existing_entries=existing_entries)
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, bom, client=client)

        self.assertEqual(result["entries_added"], 0)
        self.assertEqual(result["entries_skipped_existing"], 1)
        self.assertEqual(result["quantity_mismatches"], [])

    def test_formerly_unmatched_component_now_matched_adds_new_part_entry(self):
        unmatched_bom = pd.DataFrame(
            [
                {
                    "mpn": "NEWPART555",
                    "manufacturer": "Acme",
                    "description": "Some new part",
                    "designators": "R7",
                    "qty_per_board": "4",
                }
            ]
        )
        first_run_entries, _ = build_project_entries(unmatched_bom, FakePartsBoxClient(parts=[]))
        self.assertNotIn("entry/part-id", first_run_entries[0])

        parts_now_available = [
            {"part/id": "part-new555", "part/mpn": "NEWPART555", "part/manufacturer": "Acme"}
        ]
        client = FakePartsBoxClient(parts=parts_now_available, existing_entries=first_run_entries)
        partsbox_result = {"project_result": {"project/id": "proj-1"}}

        result = add_bom_entries_to_project(partsbox_result, unmatched_bom, client=client)

        # Known limitation, exercised rather than hidden: with no PartsBox
        # update/delete operation available, a row that becomes matched on
        # a later run cannot be reconciled with its old unmatched
        # placeholder entry. It is added as a new, distinct entry instead
        # of being silently skipped or blindly duplicated.
        self.assertEqual(result["entries_added"], 1)
        self.assertEqual(
            client.add_entries_calls[0]["entries"][0]["entry/part-id"], "part-new555"
        )


class ProductionTagLifecycleTests(unittest.TestCase):
    def test_new_storage_is_created_with_production_tag(self):
        client = FakePartsBoxClient(
            existing_project={"project/id": "p1", "project/name": "Widget"},
            existing_storage=None,
        )

        result = create_partsbox_project_and_storage("Widget", client=client)

        self.assertEqual(len(client.create_storage_calls), 1)
        self.assertEqual(client.create_storage_calls[0]["tags"], ["production"])
        self.assertFalse(result["storage_tag_missing"])

    def test_reused_storage_missing_tag_is_flagged_not_mutated(self):
        existing_storage = {"storage/id": "s1", "storage/name": "Widget", "storage/tags": ["misc"]}
        client = FakePartsBoxClient(
            existing_project={"project/id": "p1"}, existing_storage=existing_storage
        )

        result = create_partsbox_project_and_storage("Widget", client=client)

        self.assertEqual(client.create_storage_calls, [])
        self.assertTrue(result["storage_tag_missing"])
        self.assertTrue(result["storage_reused"])

    def test_reused_storage_with_tag_is_not_flagged(self):
        existing_storage = {"storage/id": "s1", "storage/name": "Widget", "storage/tags": ["production"]}
        client = FakePartsBoxClient(
            existing_project={"project/id": "p1"}, existing_storage=existing_storage
        )

        result = create_partsbox_project_and_storage("Widget", client=client)

        self.assertFalse(result["storage_tag_missing"])

    def test_existing_project_and_storage_are_reused_not_duplicated(self):
        client = FakePartsBoxClient(
            existing_project={"project/id": "p1", "project/name": "Widget"},
            existing_storage={"storage/id": "s1", "storage/name": "Widget", "storage/tags": ["production"]},
        )

        create_partsbox_project_and_storage("Widget", client=client)

        self.assertEqual(client.create_project_calls, [])
        self.assertEqual(client.create_storage_calls, [])


if __name__ == "__main__":
    unittest.main()
