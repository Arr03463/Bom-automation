import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from digikey_client import _digikey_product_to_result


class DigiKeyDescriptionPackageCharacteristicsTests(unittest.TestCase):
    """
    Added directly in response to an operator report that Find
    Replacement's results table showed blank Description/Package (and no
    way to see voltage/tolerance/current/temperature at all) for every
    DigiKey candidate -- "can't make an effective replacement without
    that". _digikey_product_to_result() previously discarded these
    fields entirely regardless of what DigiKey's response actually
    contained.
    """

    def test_nested_description_object_extracted(self):
        product = {
            "Manufacturer": {"Id": 1, "Name": "Vishay"},
            "ManufacturerProductNumber": "FSV20150V",
            "QuantityAvailable": 100,
            "Description": {
                "ProductDescription": "FSV Series Single 150 V 270 A Schottky Rectifier",
                "DetailedDescription": "Full detail text",
            },
        }
        result = _digikey_product_to_result(product)
        self.assertEqual(result.description, "FSV Series Single 150 V 270 A Schottky Rectifier")

    def test_plain_string_description_is_also_accepted(self):
        product = {
            "Manufacturer": {"Name": "Vishay"},
            "ManufacturerProductNumber": "FSV20150V",
            "QuantityAvailable": 100,
            "Description": "Plain string description",
        }
        result = _digikey_product_to_result(product)
        self.assertEqual(result.description, "Plain string description")

    def test_parameters_become_characteristics(self):
        product = {
            "Manufacturer": {"Name": "Vishay"},
            "ManufacturerProductNumber": "FSV20150V",
            "QuantityAvailable": 100,
            "Parameters": [
                {"ParameterText": "Voltage - DC Reverse (Vr) (Max)", "ValueText": "150V"},
                {"ParameterText": "Current - Average Rectified (Io)", "ValueText": "270A"},
                {"ParameterText": "Package / Case", "ValueText": "TO-277A"},
            ],
        }
        result = _digikey_product_to_result(product)
        self.assertEqual(
            result.characteristics,
            {
                "Voltage - DC Reverse (Vr) (Max)": "150V",
                "Current - Average Rectified (Io)": "270A",
                "Package / Case": "TO-277A",
            },
        )

    def test_package_shaped_parameter_populates_dedicated_package_field(self):
        product = {
            "Manufacturer": {"Name": "Vishay"},
            "ManufacturerProductNumber": "FSV20150V",
            "QuantityAvailable": 100,
            "Parameters": [{"ParameterText": "Package / Case", "ValueText": "TO-277A"}],
        }
        result = _digikey_product_to_result(product)
        self.assertEqual(result.package, "TO-277A")

    def test_missing_description_and_parameters_default_to_empty(self):
        product = {
            "Manufacturer": {"Name": "Vishay"},
            "ManufacturerProductNumber": "FSV20150V",
            "QuantityAvailable": 100,
        }
        result = _digikey_product_to_result(product)
        self.assertEqual(result.description, "")
        self.assertEqual(result.package, "")
        self.assertEqual(result.characteristics, {})

    def test_malformed_parameters_are_ignored_not_raised(self):
        product = {
            "Manufacturer": {"Name": "Vishay"},
            "ManufacturerProductNumber": "FSV20150V",
            "QuantityAvailable": 100,
            "Description": 12345,
            "Parameters": ["not a dict", {"ParameterText": "", "ValueText": "150V"}],
        }
        result = _digikey_product_to_result(product)
        self.assertEqual(result.description, "")
        self.assertEqual(result.characteristics, {})


if __name__ == "__main__":
    unittest.main()
