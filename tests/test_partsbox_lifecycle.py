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


class FakePartsBoxClient:
    """Stand-in for PartsBoxClient with no network calls, for lifecycle tests."""

    def __init__(self, parts=None, existing_project=None, existing_storage=None, existing_entries=None):
        self.parts = parts or []
        self.existing_project = existing_project
        self.existing_storage = existing_storage
        self.existing_entries = existing_entries if existing_entries is not None else []
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
