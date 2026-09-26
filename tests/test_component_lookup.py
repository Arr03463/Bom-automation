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


class PartsBoxBrowseAllTests(unittest.TestCase):
    """PartsBox Inventory reuses this exact search path to browse the
    full catalog with an empty query -- not a second listing function."""

    def test_empty_query_with_partsbox_returns_every_part(self):
        query = LookupQuery(sources=frozenset({"partsbox"}))
        client = FakePartsBoxClient(PARTSBOX_PARTS)

        results = search_components(query, partsbox_client=client)

        self.assertEqual({r["mpn"] for r in results}, {"ABC123", "XYZ789"})
        self.assertEqual(client.get_parts_calls, 1)

    def test_browse_all_still_respects_manufacturer_filter(self):
        query = LookupQuery(manufacturer="Yageo", sources=frozenset({"partsbox"}))
        client = FakePartsBoxClient(PARTSBOX_PARTS)

        results = search_components(query, partsbox_client=client)

        self.assertEqual([r["mpn"] for r in results], ["ABC123"])


class PartsBoxCharacteristicsExtractionTests(unittest.TestCase):
    def test_unrecognized_partsbox_fields_become_characteristics(self):
        parts = [
            {
                "part/id": "p1",
                "part/mpn": "CAP123",
                "part/manufacturer": "Murata",
                "part/capacitance": "10uF",
                "part/voltage": "25V",
                "part/empty_field": "",
            }
        ]
        client = FakePartsBoxClient(parts)
        results = search_components(
            LookupQuery(sources=frozenset({"partsbox"})), partsbox_client=client
        )

        result = results[0]
        self.assertEqual(result["characteristics"], {"capacitance": "10uF", "voltage": "25V"})
        # Flattened onto the top level too, for record_filter facets/ranges.
        self.assertEqual(result["capacitance"], "10uF")
        self.assertEqual(result["voltage"], "25V")
        self.assertNotIn("empty_field", result["characteristics"])

    def test_known_fields_are_not_duplicated_into_characteristics(self):
        client = FakePartsBoxClient(PARTSBOX_PARTS)
        results = search_components(
            LookupQuery(sources=frozenset({"partsbox"})), partsbox_client=client
        )

        for result in results:
            self.assertNotIn("mpn", result["characteristics"])
            self.assertNotIn("manufacturer", result["characteristics"])


class RequiredQuantityAwarenessTests(unittest.TestCase):
    def test_stock_sufficient_true_when_stock_covers_requirement(self):
        query = LookupQuery(mpn="ABC123", required_qty="10", sources=frozenset({"mouser"}))
        mouser_client = FakeSupplierSearchClient({"ABC123": [mouser_result(stock=500)]})

        results = search_components(query, mouser_client=mouser_client)

        self.assertTrue(results[0]["stock_sufficient"])

    def test_stock_sufficient_false_when_stock_is_short(self):
        query = LookupQuery(mpn="ABC123", required_qty="1000", sources=frozenset({"mouser"}))
        mouser_client = FakeSupplierSearchClient({"ABC123": [mouser_result(stock=5)]})

        results = search_components(query, mouser_client=mouser_client)

        self.assertFalse(results[0]["stock_sufficient"])

    def test_stock_sufficient_none_when_stock_unknown(self):
        query = LookupQuery(mpn="ABC123", required_qty="10", sources=frozenset({"partsbox"}))
        client = FakePartsBoxClient(PARTSBOX_PARTS)

        results = search_components(query, partsbox_client=client)

        self.assertIsNone(results[0]["stock_sufficient"])

    def test_stock_sufficient_none_when_no_requirement_given(self):
        query = LookupQuery(mpn="ABC123", sources=frozenset({"mouser"}))
        mouser_client = FakeSupplierSearchClient({"ABC123": [mouser_result(stock=500)]})

        results = search_components(query, mouser_client=mouser_client)

        self.assertIsNone(results[0]["stock_sufficient"])


class CategoryFieldTests(unittest.TestCase):
    def test_mouser_category_extracted_when_present_as_string(self):
        query = LookupQuery(mpn="ABC123", sources=frozenset({"mouser"}))
        candidate = mouser_result()
        candidate.category = "Resistors"
        mouser_client = FakeSupplierSearchClient({"ABC123": [candidate]})

        results = search_components(query, mouser_client=mouser_client)

        self.assertEqual(results[0]["category"], "Resistors")


class SupplierResultDescriptionPackageCharacteristicsWiringTests(unittest.TestCase):
    """
    _supplier_result_to_lookup_result() previously hardcoded
    description="", package="", characteristics={} regardless of what
    the client's SupplierResult actually carried -- confirms the wiring
    fix, distinct from tests/test_mouser_client.py and
    tests/test_digikey_client.py, which cover the client-side raw-API
    parsing that populates SupplierResult in the first place.
    """

    def test_mouser_description_package_characteristics_reach_the_lookup_result(self):
        query = LookupQuery(mpn="ABC123", sources=frozenset({"mouser"}))
        candidate = mouser_result()
        candidate.description = "CAP CER 1UF 16V X7R 0603"
        candidate.package = "0603"
        candidate.characteristics = {"Voltage Rating": "16V"}
        mouser_client = FakeSupplierSearchClient({"ABC123": [candidate]})

        results = search_components(query, mouser_client=mouser_client)

        self.assertEqual(results[0]["description"], "CAP CER 1UF 16V X7R 0603")
        self.assertEqual(results[0]["package"], "0603")
        # LookupResult.to_dict() also flattens characteristics onto the
        # top level (same convention PartsBox records already use), so
        # generate_facets()/apply_filters() can filter on them directly.
        self.assertEqual(results[0]["characteristics"], {"Voltage Rating": "16V"})
        self.assertEqual(results[0]["Voltage Rating"], "16V")

    def test_digikey_description_package_characteristics_reach_the_lookup_result(self):
        query = LookupQuery(mpn="ABC123", sources=frozenset({"digikey"}))
        candidate = digikey_result()
        candidate.description = "FSV Series Single 150 V Schottky Rectifier"
        candidate.package = "TO-277A"
        candidate.characteristics = {"Current - Average Rectified (Io)": "270A"}
        digikey_client = FakeSupplierSearchClient({"ABC123": [candidate]})

        results = search_components(query, digikey_client=digikey_client)

        self.assertEqual(results[0]["description"], "FSV Series Single 150 V Schottky Rectifier")
        self.assertEqual(results[0]["package"], "TO-277A")
        self.assertEqual(results[0]["characteristics"], {"Current - Average Rectified (Io)": "270A"})


class FakeRaisingSupplierClient:
    """
    Stands in for a supplier client whose search_candidates() raises --
    e.g. Mouser's real part-number search endpoint returning HTTP 400
    for free-text keywords instead of an actual part number (confirmed
    live: typing a component description into what only accepts a
    strict MPN).
    """

    def __init__(self, message="HTTP 400: no structured error details in response"):
        self.message = message

    def search_candidates(self, term):
        raise RuntimeError(self.message)


class SearchComponentsErrorIsolationTests(unittest.TestCase):
    """
    One supplier's failure must never take down the whole search or
    silently drop PartsBox/the other supplier's results -- confirmed as
    a real crash (a raw traceback shown to the operator) before this
    fix, triggered by searching a plain-English description against
    Mouser via Needs Review's "Search description instead" quick-swap.
    """

    def test_failing_mouser_does_not_raise_and_other_sources_still_return(self):
        query = LookupQuery(
            mpn="22uF +/-20% 35V X5R SMD 1206", sources=frozenset({"mouser", "digikey"})
        )
        digikey_client = FakeSupplierSearchClient(
            {"22uF +/-20% 35V X5R SMD 1206": [digikey_result()]}
        )

        # Must not raise.
        results = search_components(
            query, mouser_client=FakeRaisingSupplierClient(), digikey_client=digikey_client
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "DigiKey")

    def test_failure_is_reported_via_the_errors_list_when_provided(self):
        query = LookupQuery(mpn="bad query", sources=frozenset({"mouser"}))
        errors = []

        results = search_components(
            query,
            mouser_client=FakeRaisingSupplierClient("HTTP 400: no structured error details in response"),
            errors=errors,
        )

        self.assertEqual(results, [])
        self.assertEqual(len(errors), 1)
        source, message = errors[0]
        self.assertEqual(source, "mouser")
        self.assertIn("400", message)

    def test_errors_default_of_none_does_not_require_callers_to_pass_a_list(self):
        """
        Every existing caller that doesn't know about the new `errors`
        parameter must keep working exactly as before -- just without
        crashing on a bad query.
        """
        query = LookupQuery(mpn="bad query", sources=frozenset({"digikey"}))

        results = search_components(query, digikey_client=FakeRaisingSupplierClient())

        self.assertEqual(results, [])

    def test_both_suppliers_failing_reports_both_without_raising(self):
        query = LookupQuery(mpn="bad query", sources=frozenset({"mouser", "digikey"}))
        errors = []

        results = search_components(
            query,
            mouser_client=FakeRaisingSupplierClient("mouser boom"),
            digikey_client=FakeRaisingSupplierClient("digikey boom"),
            errors=errors,
        )

        self.assertEqual(results, [])
        failed_sources = {source for source, _ in errors}
        self.assertEqual(failed_sources, {"mouser", "digikey"})


if __name__ == "__main__":
    unittest.main()
