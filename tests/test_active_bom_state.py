import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from active_bom_state import ActiveBomState


def make_dataframe():
    return pd.DataFrame(
        [
            {"mpn": "ABC123", "manufacturer": "Yageo", "status": "clean"},
            {"mpn": "", "manufacturer": "TI", "status": "missing_mpn"},
            {"mpn": "XYZ789", "manufacturer": "STMicro", "status": "clean"},
        ]
    )


class ActiveBomStateTests(unittest.TestCase):
    def test_rows_contains_every_row_with_stable_row_ids(self):
        df = make_dataframe()
        state = ActiveBomState(df, run_id="run-1")

        rows = state.rows()

        self.assertEqual(len(rows), 3)
        self.assertEqual([row["row_id"] for row in rows], ["run-1:0", "run-1:1", "run-1:2"])

    def test_review_items_derives_from_canonical_state(self):
        df = make_dataframe()
        state = ActiveBomState(df, run_id="run-1")

        review = state.review_items()

        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]["row_id"], "run-1:1")
        self.assertEqual(review[0]["mpn"], "")

    def test_updating_a_row_is_reflected_when_rows_are_regenerated(self):
        df = make_dataframe()
        state = ActiveBomState(df, run_id="run-1")

        state.update_row("run-1:1", {"mpn": "NEWPART", "status": "clean"})

        rows = state.rows()
        updated_row = next(row for row in rows if row["row_id"] == "run-1:1")
        self.assertEqual(updated_row["mpn"], "NEWPART")
        self.assertEqual(updated_row["status"], "clean")

    def test_updating_a_row_removes_it_from_review_when_regenerated(self):
        df = make_dataframe()
        state = ActiveBomState(df, run_id="run-1")

        # Before the update, row 1 needs review.
        self.assertEqual(len(state.review_items()), 1)

        state.update_row("run-1:1", {"mpn": "NEWPART", "status": "clean"})

        # review_items() recomputes from the canonical DataFrame each call
        # -- it must not still report a row that no longer needs review.
        self.assertEqual(state.review_items(), [])

    def test_no_second_authoritative_copy_of_the_dataframe(self):
        df = make_dataframe()
        state = ActiveBomState(df, run_id="run-1")

        # The state wraps the SAME DataFrame object -- a mutation made
        # directly to the original object (as sourcing/PartsBox steps do
        # today) is visible through the state, with no separate copy to
        # resynchronize.
        self.assertIs(state.dataframe, df)

        df.at[0, "manufacturer"] = "Changed Directly"
        rows = state.rows()
        self.assertEqual(rows[0]["manufacturer"], "Changed Directly")

    def test_get_row_returns_none_for_unknown_row_id(self):
        df = make_dataframe()
        state = ActiveBomState(df, run_id="run-1")

        self.assertIsNone(state.get_row("run-1:999"))
        self.assertIsNone(state.get_row("different-run:0"))

    def test_update_row_raises_for_unknown_row_id(self):
        df = make_dataframe()
        state = ActiveBomState(df, run_id="run-1")

        with self.assertRaises(KeyError):
            state.update_row("run-1:999", {"status": "clean"})

    def test_get_row_includes_derived_fields(self):
        df = make_dataframe()
        state = ActiveBomState(df, run_id="run-1")

        row = state.get_row("run-1:1")

        self.assertEqual(row["source"], "None")
        self.assertEqual(row["result_status"], "Needs Review")


class SourceAndStatusDerivationTests(unittest.TestCase):
    def test_source_and_status_are_distinct_concepts(self):
        df = pd.DataFrame(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "selected_supplier": "Mouser",
                    "sourcing_status": "sourced_mouser",
                },
                {
                    "mpn": "XYZ789",
                    "manufacturer": "TI",
                    "status": "clean",
                    "selected_supplier": "",
                    "sourcing_status": "check_wall_inventory",
                },
            ]
        )
        state = ActiveBomState(df, run_id="run-1")
        rows = state.rows()

        # A Mouser-sourced row is Source=Mouser, Status=Ready -- two
        # separate fields, neither one standing in for the other.
        self.assertEqual(rows[0]["source"], "Mouser")
        self.assertEqual(rows[0]["result_status"], "Ready")

        # A row needing review still has no usable source.
        self.assertEqual(rows[1]["source"], "None")
        self.assertEqual(rows[1]["result_status"], "Needs Review")

    def test_partsbox_matched_row_is_ready(self):
        df = pd.DataFrame(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "partsbox_match_status": "matched",
                    "partsbox_part_id": "part-1",
                }
            ]
        )
        state = ActiveBomState(df, run_id="run-1")
        row = state.rows()[0]

        self.assertEqual(row["source"], "PartsBox")
        self.assertEqual(row["result_status"], "Ready")

    def test_partsbox_unmatched_row_with_no_sourcing_is_not_found(self):
        df = pd.DataFrame(
            [
                {
                    "mpn": "ABC123",
                    "manufacturer": "Yageo",
                    "status": "clean",
                    "partsbox_match_status": "unmatched",
                }
            ]
        )
        state = ActiveBomState(df, run_id="run-1")
        row = state.rows()[0]

        self.assertEqual(row["source"], "None")
        self.assertEqual(row["result_status"], "Not Found")

    def test_review_reason_is_populated_for_review_rows_only(self):
        df = pd.DataFrame(
            [
                {"mpn": "ABC123", "manufacturer": "Yageo", "status": "clean"},
                {"mpn": "", "manufacturer": "TI", "status": "missing_mpn", "notes": "missing mpn"},
            ]
        )
        state = ActiveBomState(df, run_id="run-1")
        rows = state.rows()

        self.assertEqual(rows[0]["review_reason"], "")
        self.assertIn("missing mpn", rows[1]["review_reason"])

    def test_summary_counts_derive_from_canonical_state(self):
        df = pd.DataFrame(
            [
                {
                    "mpn": "A",
                    "manufacturer": "M",
                    "status": "clean",
                    "selected_supplier": "Mouser",
                    "sourcing_status": "sourced_mouser",
                },
                {
                    "mpn": "B",
                    "manufacturer": "M",
                    "status": "clean",
                    "selected_supplier": "DigiKey",
                    "sourcing_status": "sourced_digikey",
                },
                {
                    "mpn": "C",
                    "manufacturer": "M",
                    "status": "clean",
                    "partsbox_match_status": "matched",
                    "partsbox_part_id": "p1",
                },
                {"mpn": "", "manufacturer": "M", "status": "missing_mpn"},
            ]
        )
        state = ActiveBomState(df, run_id="run-1")

        counts = state.summary_counts()

        self.assertEqual(
            counts,
            {"total_parts": 4, "partsbox": 1, "mouser": 1, "digikey": 1, "needs_review": 1},
        )

    def test_summary_counts_reflect_update_row(self):
        df = pd.DataFrame(
            [{"mpn": "", "manufacturer": "M", "status": "missing_mpn"}]
        )
        state = ActiveBomState(df, run_id="run-1")

        self.assertEqual(state.summary_counts()["needs_review"], 1)

        state.update_row("run-1:0", {"mpn": "NEWPART", "status": "clean"})

        self.assertEqual(state.summary_counts()["needs_review"], 0)


if __name__ == "__main__":
    unittest.main()
