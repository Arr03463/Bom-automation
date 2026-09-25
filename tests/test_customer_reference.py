import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from customer_reference import (
    MAX_LENGTH,
    build_inventory_reference,
    build_project_reference,
    build_rnd_reference,
    normalize_component,
    validate_customer_reference,
)


class BuildReferenceTests(unittest.TestCase):
    def test_inventory_reference(self):
        self.assertEqual(build_inventory_reference("a1"), "INV-A1")

    def test_project_reference_single_pcb(self):
        self.assertEqual(build_project_reference("arm", ["rxctr"]), "PRJ-ARM-RXCTR")

    def test_project_reference_matches_spec_examples(self):
        self.assertEqual(build_project_reference("ath", ["dab"]), "PRJ-ATH-DAB")
        self.assertEqual(build_project_reference("ath", ["buzz"]), "PRJ-ATH-BUZZ")

    def test_project_reference_multiple_pcb_codes_joined_with_underscore(self):
        self.assertEqual(build_project_reference("ath", ["dab", "buzz"]), "PRJ-ATH-DAB_BUZZ")

    def test_project_reference_preserves_selection_order(self):
        self.assertEqual(
            build_project_reference("ath", ["buzz", "dab"]), "PRJ-ATH-BUZZ_DAB"
        )

    def test_rnd_reference(self):
        self.assertEqual(build_rnd_reference("arm", "aaron"), "RND-ARM-AARON")

    def test_rnd_reference_trims_owner_whitespace(self):
        self.assertEqual(build_rnd_reference("arm", "  aaron  "), "RND-ARM-AARON")

    def test_normalize_component_uppercases_and_trims(self):
        self.assertEqual(normalize_component("  a12  "), "A12")


class ValidateCustomerReferenceTests(unittest.TestCase):
    def test_valid_reference_passes(self):
        result = validate_customer_reference("PRJ-ARM-RXCTR")
        self.assertTrue(result.valid)
        self.assertEqual(result.errors, [])

    def test_multi_pcb_reference_from_spec_is_valid(self):
        result = validate_customer_reference("PRJ-ATH-DAB_BUZZ")
        self.assertTrue(result.valid)

    def test_empty_value_is_invalid(self):
        result = validate_customer_reference("")
        self.assertFalse(result.valid)

    def test_too_long_value_is_invalid_not_truncated(self):
        too_long = "PRJ-VERY-LONG-PROJECT-VERY-LONG-PCB"
        self.assertGreater(len(too_long), MAX_LENGTH)

        result = validate_customer_reference(too_long)

        self.assertFalse(result.valid)
        self.assertEqual(result.value, too_long)  # never silently shortened
        self.assertTrue(any("30" in error for error in result.errors))

    def test_exactly_max_length_is_valid(self):
        value = "PRJ-" + ("A" * 26)  # 4 + 26 = 30
        self.assertEqual(len(value), MAX_LENGTH)
        self.assertTrue(validate_customer_reference(value).valid)

    def test_lowercase_value_is_invalid(self):
        result = validate_customer_reference("prj-arm-rxctr")
        self.assertFalse(result.valid)

    def test_spaces_are_invalid(self):
        result = validate_customer_reference("PRJ-ARM RXCTR")
        self.assertFalse(result.valid)

    def test_disallowed_characters_are_invalid(self):
        result = validate_customer_reference("PRJ-ARM-RXCTR!")
        self.assertFalse(result.valid)

    def test_missing_recognized_prefix_is_invalid(self):
        result = validate_customer_reference("XYZ-ARM-RXCTR")
        self.assertFalse(result.valid)

    def test_underscore_allowed_for_multi_pcb(self):
        result = validate_customer_reference("PRJ-ATH-DAB_BUZZ_RXCTR")
        self.assertTrue(result.valid)


if __name__ == "__main__":
    unittest.main()
