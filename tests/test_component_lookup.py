import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from component_lookup import LookupQuery, build_query_from_bom_row, search_components
from sourcing_engine import SupplierResult


class FakePartsBoxClient:
    def __init__(self, parts):
        self.parts = parts
        self.get_parts_calls = 0

    def get_parts(self):
        self.get_parts_calls += 1
        return self.parts


class FakeSupplierSearchClient:
    """Stands in for either MouserClient or DigiKeyClient -- both expose
    the same search_candidates(term) -> list[SupplierResult] shape."""

    def __init__(self, candidates_by_term=None):
        self.candidates_by_term = candidates_by_term or {}
        self.calls = []

    def search_candidates(self, term):
        self.calls.append(term)
        return self.candidates_by_term.get(term, [])


PARTSBOX_PARTS = [
    {
        "part/id": "p1",
        "part/mpn": "ABC123",
        "part/manufacturer": "Yageo",
        "part/description": "10k Resistor",
        "part/category": "Resistor",
        "part/package": "0603",
    },
    {
        "part/id": "p2",
        "part/mpn": "XYZ789",
        "part/manufacturer": "TI",
        "part/description": "Op Amp",
        "part/category": "IC",
        "part/package": "SOIC-8",
    },
]


def mouser_result(mpn="ABC123", manufacturer="Yageo", stock=500, supplier_part_number="603-ABC123"):
    return SupplierResult(
        supplier="Mouser",
        manufacturer=manufacturer,
        mpn=mpn,
        stock=stock,
        unit_price="0.05",
        supplier_part_number=supplier_part_number,
    )


def digikey_result(mpn="ABC123", manufacturer="Yageo", stock=1000, supplier_part_number="ABC123-ND"):
    return SupplierResult(
        supplier="DigiKey",
        manufacturer=manufacturer,
        mpn=mpn,
        stock=stock,
        unit_price="0.04",
        supplier_part_number=supplier_part_number,
    )


class ComponentLookupSourceTests(unittest.TestCase):
    def test_default_sources_is_partsbox_only(self):
        query = LookupQuery(mpn="ABC123")
        self.assertEqual(query.sources, frozenset({"partsbox"}))

    def test_partsbox_only_search_returns_partsbox_results(self):
        query = LookupQuery(mpn="ABC123", sources=frozenset({"partsbox"}))
        partsbox_client = FakePartsBoxClient(PARTSBOX_PARTS)
        mouser_client = FakeSupplierSearchClient()
        digikey_client = FakeSupplierSearchClient()

        results = search_components(
            query,
            partsbox_client=partsbox_client,
            mouser_client=mouser_client,
            digikey_client=digikey_client,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "PartsBox")
        self.assertEqual(results[0]["mpn"], "ABC123")
        # Sources not enabled must never be queried.
        self.assertEqual(mouser_client.calls, [])
        self.assertEqual(digikey_client.calls, [])

    def test_mouser_enabled_includes_mouser_results(self):
        query = LookupQuery(mpn="ABC123", sources=frozenset({"partsbox", "mouser"}))
        partsbox_client = FakePartsBoxClient(PARTSBOX_PARTS)
        mouser_client = FakeSupplierSearchClient({"ABC123": [mouser_result()]})
        digikey_client = FakeSupplierSearchClient()

        results = search_components(
            query,
            partsbox_client=partsbox_client,
            mouser_client=mouser_client,
            digikey_client=digikey_client,
        )

        sources = {result["source"] for result in results}
        self.assertEqual(sources, {"PartsBox", "Mouser"})
        self.assertEqual(mouser_client.calls, ["ABC123"])
        self.assertEqual(digikey_client.calls, [])

    def test_digikey_enabled_includes_digikey_results(self):
        query = LookupQuery(mpn="ABC123", sources=frozenset({"digikey"}))
        digikey_client = FakeSupplierSearchClient({"ABC123": [digikey_result()]})
        mouser_client = FakeSupplierSearchClient()
        partsbox_client = FakePartsBoxClient(PARTSBOX_PARTS)

        results = search_components(
            query,
            partsbox_client=partsbox_client,
            mouser_client=mouser_client,
            digikey_client=digikey_client,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "DigiKey")
        self.assertEqual(partsbox_client.get_parts_calls, 0)

    def test_all_sources_enabled_equals_union_of_each_alone(self):
        """
        Source toggles must not create separate lookup engines -- enabling
        all three sources together must return exactly the union of what
        each source returns on its own, proving one shared code path
        composes rather than branching into different combined logic.
        """
        partsbox_client = FakePartsBoxClient(PARTSBOX_PARTS)
        mouser_client = FakeSupplierSearchClient({"ABC123": [mouser_result()]})
        digikey_client = FakeSupplierSearchClient({"ABC123": [digikey_result()]})

        partsbox_only = search_components(
            LookupQuery(mpn="ABC123", sources=frozenset({"partsbox"})),
            partsbox_client=FakePartsBoxClient(PARTSBOX_PARTS),
        )
        mouser_only = search_components(
            LookupQuery(mpn="ABC123", sources=frozenset({"mouser"})),
            mouser_client=FakeSupplierSearchClient({"ABC123": [mouser_result()]}),
        )
        digikey_only = search_components(
            LookupQuery(mpn="ABC123", sources=frozenset({"digikey"})),
            digikey_client=FakeSupplierSearchClient({"ABC123": [digikey_result()]}),
        )

        combined = search_components(
            LookupQuery(mpn="ABC123", sources=frozenset({"partsbox", "mouser", "digikey"})),
            partsbox_client=partsbox_client,
            mouser_client=mouser_client,
            digikey_client=digikey_client,
        )

        self.assertEqual(len(combined), len(partsbox_only) + len(mouser_only) + len(digikey_only))
        combined_sources = sorted(result["source"] for result in combined)
        self.assertEqual(combined_sources, ["DigiKey", "Mouser", "PartsBox"])

    def test_manufacturer_alias_filters_supplier_results(self):
        query = LookupQuery(mpn="ABC123", manufacturer="TI", sources=frozenset({"mouser"}))
        mouser_client = FakeSupplierSearchClient(
            {"ABC123": [mouser_result(manufacturer="Texas Instruments")]}
        )

        results = search_components(query, mouser_client=mouser_client)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["manufacturer"], "Texas Instruments")

    def test_manufacturer_mismatch_excludes_supplier_result(self):
        query = LookupQuery(mpn="ABC123", manufacturer="Murata", sources=frozenset({"mouser"}))
        mouser_client = FakeSupplierSearchClient({"ABC123": [mouser_result(manufacturer="Yageo")]})

        results = search_components(query, mouser_client=mouser_client)

        self.assertEqual(results, [])

    def test_manufacturer_only_search_matches_partsbox_by_manufacturer(self):
        query = LookupQuery(manufacturer="Yageo", sources=frozenset({"partsbox"}))
        partsbox_client = FakePartsBoxClient(PARTSBOX_PARTS)

        results = search_components(query, partsbox_client=partsbox_client)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["mpn"], "ABC123")

    def test_explicitly_empty_source_set_returns_no_results_not_partsbox_fallback(self):
        query = LookupQuery(mpn="ABC123", sources=frozenset())
        partsbox_client = FakePartsBoxClient(PARTSBOX_PARTS)
        mouser_client = FakeSupplierSearchClient({"ABC123": [mouser_result()]})
        digikey_client = FakeSupplierSearchClient({"ABC123": [digikey_result()]})

        results = search_components(
            query,
            partsbox_client=partsbox_client,
            mouser_client=mouser_client,
            digikey_client=digikey_client,
        )

        self.assertEqual(results, [])
        self.assertEqual(partsbox_client.get_parts_calls, 0)
        self.assertEqual(mouser_client.calls, [])
        self.assertEqual(digikey_client.calls, [])

    def test_empty_query_does_not_call_supplier_search(self):
        query = LookupQuery(sources=frozenset({"mouser", "digikey"}))
        mouser_client = FakeSupplierSearchClient()
        digikey_client = FakeSupplierSearchClient()

        results = search_components(query, mouser_client=mouser_client, digikey_client=digikey_client)

        self.assertEqual(results, [])
        self.assertEqual(mouser_client.calls, [])
        self.assertEqual(digikey_client.calls, [])

    def test_result_preserves_raw_payload(self):
        query = LookupQuery(mpn="ABC123", sources=frozenset({"partsbox"}))
        partsbox_client = FakePartsBoxClient(PARTSBOX_PARTS)

        results = search_components(query, partsbox_client=partsbox_client)

        self.assertEqual(results[0]["raw"]["part/id"], "p1")


class BuildQueryFromBomRowTests(unittest.TestCase):
    def test_prepopulates_from_known_bom_fields(self):
        row = {
            "mpn": "ABC123",
            "manufacturer": "Yageo",
            "description": "10k Resistor 1% 0603",
            "required_qty": "50",
        }

        query = build_query_from_bom_row(row)

        self.assertEqual(query.mpn, "ABC123")
        self.assertEqual(query.manufacturer, "Yageo")
        self.assertEqual(query.keywords, "10k Resistor 1% 0603")
        self.assertEqual(query.required_qty, "50")

    def test_defaults_to_mouser_and_digikey_for_find_replacement(self):
        query = build_query_from_bom_row({"mpn": "ABC123"})
        self.assertEqual(query.sources, frozenset({"mouser", "digikey"}))

    def test_check_partsbox_reuses_same_builder_with_partsbox_sources(self):
        query = build_query_from_bom_row({"mpn": "ABC123"}, sources={"partsbox"})
        self.assertEqual(query.sources, frozenset({"partsbox"}))

    def test_does_not_fabricate_missing_fields(self):
        query = build_query_from_bom_row({"mpn": "ABC123"})

        self.assertEqual(query.manufacturer, "")
        self.assertEqual(query.package, "")
        self.assertEqual(query.voltage, "")
        self.assertEqual(query.characteristics, {})


if __name__ == "__main__":
    unittest.main()
