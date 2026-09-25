import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from inventory_location_recommender import (
    CONFIDENCE_EXACT_PART,
    CONFIDENCE_LOW,
    CONFIDENCE_MANUAL,
    CONFIDENCE_SIMILAR_FAMILY,
    CONFIDENCE_STRONG_SIMILARITY,
    recommend_location,
)

STORAGE_A12 = {"storage/id": "storage-a12", "storage/name": "A12"}
STORAGE_A13 = {"storage/id": "storage-a13", "storage/name": "A13"}
STORAGE_A10 = {"storage/id": "storage-a10", "storage/name": "A10"}


class FakePartsBoxClient:
    """
    Stand-in for PartsBoxClient with no network calls -- mirrors the
    fake client pattern already used in tests/test_partsbox_lifecycle.py.
    """

    def __init__(self, parts=None, storage_locations=None):
        self.parts = parts or []
        self.storage_locations = storage_locations or [STORAGE_A10, STORAGE_A12, STORAGE_A13]

    def get_parts(self):
        return self.parts

    def find_part_by_mpn_and_manufacturer(self, mpn, manufacturer=""):
        target_mpn = str(mpn or "").strip().lower()
        for part in self.parts:
            part_mpn = str(part.get("part/mpn") or part.get("part/name") or "").strip().lower()
            if part_mpn == target_mpn:
                return part
        return None

    def list_storage_locations(self):
        return {"data": self.storage_locations}


def _ledger(*entries):
    """entries: (storage_id, quantity) pairs."""
    return [{"stock/quantity": qty, "stock/storage-id": storage_id} for storage_id, qty in entries]


class ExactPartRecommendationTests(unittest.TestCase):
    def test_single_positive_storage_is_exact_part(self):
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "RC0603FR-0710KL",
                    "part/manufacturer": "Yageo",
                    "part/stock": _ledger(("storage-a12", 10), ("storage-a12", -1)),
                }
            ]
        )

        result = recommend_location("RC0603FR-0710KL", "Yageo", partsbox_client=client)

        self.assertEqual(result.confidence, CONFIDENCE_EXACT_PART)
        self.assertEqual(result.location, "A12")

    def test_ledger_netting_to_zero_or_negative_is_not_a_current_location(self):
        """
        Codex PartsBox stock-ledger caution: an exact part whose ledger
        nets to <= 0 everywhere must not be reported as currently stored
        there -- it must fall through to similarity analysis instead.
        """
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "DEPLETED123",
                    "part/manufacturer": "Yageo",
                    "part/stock": _ledger(("storage-a12", 10), ("storage-a12", -10)),
                    "part/description": "10k Resistor 1% 0603",
                }
            ]
        )

        result = recommend_location("DEPLETED123", "Yageo", "10k Resistor 1% 0603", partsbox_client=client)

        # Falls through to similarity (Priority 2/3) rather than claiming
        # Exact Part with no real evidence -- with no other parts in
        # PartsBox to compare against, that lands on Manual Selection.
        self.assertEqual(result.confidence, CONFIDENCE_MANUAL)

    def test_multiple_positive_storages_lowers_confidence_and_picks_highest_quantity(self):
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "SPLIT123",
                    "part/manufacturer": "Yageo",
                    "part/stock": _ledger(("storage-a12", 5), ("storage-a13", 20)),
                }
            ]
        )

        result = recommend_location("SPLIT123", "Yageo", partsbox_client=client)

        self.assertEqual(result.confidence, CONFIDENCE_STRONG_SIMILARITY)
        self.assertEqual(result.location, "A13")

    def test_never_takes_first_or_last_ledger_entry_blindly(self):
        """
        The ledger has a positive first entry followed by enough negative
        entries to net negative -- if the recommender took the first (or
        last) entry naively it would wrongly recommend storage-a12.
        """
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "TRAP123",
                    "part/manufacturer": "Yageo",
                    "part/stock": _ledger(
                        ("storage-a12", 100), ("storage-a12", -50), ("storage-a12", -50), ("storage-a13", 7)
                    ),
                }
            ]
        )

        result = recommend_location("TRAP123", "Yageo", partsbox_client=client)

        self.assertEqual(result.confidence, CONFIDENCE_EXACT_PART)
        self.assertEqual(result.location, "A13")

    def test_no_ledger_at_all_falls_through_to_similarity(self):
        client = FakePartsBoxClient(
            parts=[{"part/mpn": "NOLEDGER123", "part/manufacturer": "Yageo"}]
        )

        result = recommend_location("NOLEDGER123", "Yageo", partsbox_client=client)

        self.assertEqual(result.confidence, CONFIDENCE_MANUAL)


class SimilarityRecommendationTests(unittest.TestCase):
    def test_structured_category_package_match_is_strong_similarity(self):
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "SIMILAR1",
                    "part/manufacturer": "Yageo",
                    "part/category": "Resistor",
                    "part/package": "0603",
                    "part/description": "4.7k Resistor 1% 0603",
                    "part/stock": _ledger(("storage-a12", 50)),
                },
                {
                    "part/mpn": "SIMILAR2",
                    "part/manufacturer": "Yageo",
                    "part/category": "Resistor",
                    "part/package": "0603",
                    "part/description": "22k Resistor 1% 0603",
                    "part/stock": _ledger(("storage-a12", 30)),
                },
            ]
        )

        result = recommend_location(
            "NEWVALUE123", "Yageo", "10k Resistor 1% 0603", partsbox_client=client
        )

        self.assertEqual(result.confidence, CONFIDENCE_STRONG_SIMILARITY)
        self.assertEqual(result.location, "A12")

    def test_description_only_overlap_with_manufacturer_match_reaches_strong_similarity(self):
        # Confirmed live: this account's real PartsBox data has neither
        # category nor package populated -- the recommender must still
        # produce a usable result from manufacturer + description overlap
        # alone.
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "DESC1",
                    "part/manufacturer": "Yageo",
                    "part/description": "10k Resistor 1% 0603",
                    "part/stock": _ledger(("storage-a12", 50)),
                },
            ]
        )

        result = recommend_location(
            "DESC2", "Yageo", "10k Resistor 1% 0603", partsbox_client=client
        )

        self.assertIn(result.confidence, (CONFIDENCE_STRONG_SIMILARITY, CONFIDENCE_SIMILAR_FAMILY))
        self.assertEqual(result.location, "A12")

    def test_similar_parts_split_across_locations_is_low_confidence(self):
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "SPLITSIM1",
                    "part/manufacturer": "Yageo",
                    "part/category": "Resistor",
                    "part/package": "0603",
                    "part/stock": _ledger(("storage-a10", 10)),
                },
                {
                    "part/mpn": "SPLITSIM2",
                    "part/manufacturer": "Yageo",
                    "part/category": "Resistor",
                    "part/package": "0603",
                    "part/stock": _ledger(("storage-a12", 10)),
                },
                {
                    "part/mpn": "SPLITSIM3",
                    "part/manufacturer": "Yageo",
                    "part/category": "Resistor",
                    "part/package": "0603",
                    "part/stock": _ledger(("storage-a13", 10)),
                },
            ]
        )

        result = recommend_location("NEWSPLIT", "Yageo", partsbox_client=client)

        self.assertEqual(result.confidence, CONFIDENCE_LOW)

    def test_no_similar_parts_is_manual_selection_required(self):
        client = FakePartsBoxClient(parts=[])

        result = recommend_location("UNKNOWNPART", "Acme", partsbox_client=client)

        self.assertEqual(result.confidence, CONFIDENCE_MANUAL)
        self.assertEqual(result.location, "")

    def test_similar_parts_with_no_determinable_location_is_manual_selection(self):
        client = FakePartsBoxClient(
            parts=[
                {
                    "part/mpn": "SIMILARNOLOC",
                    "part/manufacturer": "Yageo",
                    "part/category": "Resistor",
                    "part/package": "0603",
                    # No part/stock at all.
                },
            ]
        )

        result = recommend_location("NEEDSLOC", "Yageo", partsbox_client=client)

        self.assertEqual(result.confidence, CONFIDENCE_MANUAL)


class RecommendationIsNeverFinalTests(unittest.TestCase):
    def test_recommendation_never_writes_anything(self):
        """
        recommend_location() is read-only: it must never call any
        PartsBox write operation. FakePartsBoxClient has no create_*/
        update_* methods at all, so any attempt to call one would raise
        AttributeError -- proving none was attempted.
        """
        client = FakePartsBoxClient(
            parts=[{"part/mpn": "X", "part/manufacturer": "Y", "part/stock": _ledger(("storage-a12", 1))}]
        )

        recommend_location("X", "Y", partsbox_client=client)  # must not raise


if __name__ == "__main__":
    unittest.main()
