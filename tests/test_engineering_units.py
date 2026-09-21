import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_FOLDER = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_FOLDER))

from engineering_units import parse_engineering_value, value_in_range


class ParseEngineeringValueTests(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(parse_engineering_value("5"), 5.0)

    def test_number_with_unit_suffix(self):
        self.assertEqual(parse_engineering_value("25V"), 25.0)
        self.assertEqual(parse_engineering_value("25 V"), 25.0)
        self.assertEqual(parse_engineering_value("3A"), 3.0)

    def test_si_prefix_with_unit(self):
        self.assertAlmostEqual(parse_engineering_value("10uF"), 10e-6)
        self.assertAlmostEqual(parse_engineering_value("100nH"), 100e-9)
        self.assertEqual(parse_engineering_value("4.7k"), 4700.0)

    def test_tolerance_percent_and_plus_minus(self):
        self.assertEqual(parse_engineering_value("10%"), 10.0)
        self.assertEqual(parse_engineering_value("±10%"), 10.0)
        self.assertEqual(parse_engineering_value("+/-10%"), 10.0)

    def test_negative_number(self):
        self.assertEqual(parse_engineering_value("-5"), -5.0)

    def test_none_and_blank_return_none(self):
        self.assertIsNone(parse_engineering_value(None))
        self.assertIsNone(parse_engineering_value(""))
        self.assertIsNone(parse_engineering_value("   "))

    def test_non_numeric_text_returns_none(self):
        self.assertIsNone(parse_engineering_value("obsolete"))
        self.assertIsNone(parse_engineering_value("SOIC-8"))

    def test_numeric_value_passthrough(self):
        self.assertEqual(parse_engineering_value(25), 25.0)
        self.assertEqual(parse_engineering_value(25.5), 25.5)


class ValueInRangeTests(unittest.TestCase):
    def test_within_bounds(self):
        self.assertTrue(value_in_range(25.0, minimum=10, maximum=30))

    def test_below_minimum(self):
        self.assertFalse(value_in_range(5.0, minimum=10, maximum=30))

    def test_above_maximum(self):
        self.assertFalse(value_in_range(35.0, minimum=10, maximum=30))

    def test_unbounded_minimum(self):
        self.assertTrue(value_in_range(1000.0, minimum=None, maximum=2000))

    def test_unbounded_maximum(self):
        self.assertTrue(value_in_range(1000.0, minimum=500, maximum=None))

    def test_no_bounds_always_true_for_known_value(self):
        self.assertTrue(value_in_range(5.0, minimum=None, maximum=None))

    def test_none_value_never_matches(self):
        self.assertFalse(value_in_range(None, minimum=None, maximum=None))
        self.assertFalse(value_in_range(None, minimum=10, maximum=30))


if __name__ == "__main__":
    unittest.main()
