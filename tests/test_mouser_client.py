import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from mouser_client import _mouser_part_to_result


class MouserDescriptionPackageCharacteristicsTests(unittest.TestCase):
    """
    Added directly in response to an operator report that Find
    Replacement's results table showed blank Description/Package (and no
    way to see voltage/tolerance/current/temperature at all) for every
    Mouser candidate -- "can't make an effective replacement without
    that". _mouser_part_to_result() previously discarded these fields
    entirely regardless of what Mouser's response actually contained.
    """

    def test_description_is_extracted(self):
        part = {
            "Category": "Capacitors",
            "Manufacturer": "Murata",
            "ManufacturerPartNumber": "GRM188R71C105KA12D",
            "MouserPartNumber": "81-GRM188R71C105KA12D",
            "Description": "CAP CER 1UF 16V X7R 0603",
            "Availability": "5000 In Stock",
        }
        result = _mouser_part_to_result(part)
        self.assertEqual(result.description, "CAP CER 1UF 16V X7R 0603")

    def test_product_attributes_become_characteristics(self):
        part = {
            "Manufacturer": "Murata",
            "ManufacturerPartNumber": "GRM188R71C105KA12D",
            "Availability": "5000 In Stock",
            "ProductAttributes": [
                {"AttributeName": "Voltage Rating", "AttributeValue": "16V"},
                {"AttributeName": "Tolerance", "AttributeValue": "±10%"},
                {"AttributeName": "Case/Package", "AttributeValue": "0603"},
            ],
        }
        result = _mouser_part_to_result(part)
        self.assertEqual(
            result.characteristics,
            {"Voltage Rating": "16V", "Tolerance": "±10%", "Case/Package": "0603"},
        )

    def test_package_shaped_attribute_populates_dedicated_package_field(self):
        part = {
            "Manufacturer": "Murata",
            "ManufacturerPartNumber": "GRM188R71C105KA12D",
            "Availability": "5000 In Stock",
            "ProductAttributes": [{"AttributeName": "Case/Package", "AttributeValue": "0603"}],
        }
        result = _mouser_part_to_result(part)
        self.assertEqual(result.package, "0603")

    def test_missing_description_and_attributes_default_to_empty(self):
        """
        Best-effort/defensive, like the existing category handling -- a
        response without these fields must not raise, and must not
        fabricate a value.
        """
        part = {
            "Manufacturer": "Murata",
            "ManufacturerPartNumber": "GRM188R71C105KA12D",
            "Availability": "5000 In Stock",
        }
        result = _mouser_part_to_result(part)
        self.assertEqual(result.description, "")
        self.assertEqual(result.package, "")
        self.assertEqual(result.characteristics, {})

    def test_non_string_description_and_malformed_attributes_are_ignored_not_raised(self):
        part = {
            "Manufacturer": "Murata",
            "ManufacturerPartNumber": "GRM188R71C105KA12D",
            "Availability": "5000 In Stock",
            "Description": {"unexpected": "shape"},
            "ProductAttributes": ["not a dict", {"AttributeName": "", "AttributeValue": "16V"}],
        }
        result = _mouser_part_to_result(part)
        self.assertEqual(result.description, "")
        self.assertEqual(result.characteristics, {})


if __name__ == "__main__":
    unittest.main()
