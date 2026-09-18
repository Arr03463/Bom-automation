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


if __name__ == "__main__":
    unittest.main()
